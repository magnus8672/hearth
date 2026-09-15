"""Portable private vaults. Database revisions are authoritative, files are projections."""
import hashlib
import io
import json
import os
import re
import threading
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

import yaml
from fastapi import HTTPException
from sqlalchemy import text

from hearth.database import scoped_session

README = '''# Your hearth memory

Extract this ZIP into a new folder, then choose **Open folder as vault** in Obsidian.

- `notes/`: your editable memory notes. Preferences are considered for every private text reply; other notes are found by matching words.
- `messages/`: editable individual chat messages. Correct the text below the frontmatter. Keep IDs, scope and revision fields intact.
- `conversations/`: generated full transcripts, including archived chats. JSONL keeps exact message text and source metadata.
- `revisions.jsonl`: original text and subsequent corrections, plus note revisions and removal records.
- `graph.json`: explicit links in this private vault, suitable for the optional offline Graphify adapter.

To apply an edit, open **Memory** in hearth and choose **Import edited Markdown**. A stale revision is rejected so another edit cannot be overwritten. New plain Markdown files become new notes. This build does not continuously synchronize desktop files. Import individual notes or messages, not generated transcripts. Generated files on the server preserve unexpected edits in `conflicts/` before rebuilding.

Removing a memory note stops recall immediately; revision history is retained. Excluding a chat stops cross-session recall, while its transcript stays in your archive and export. Exports already on your computer remain under your control. Use a separate vault and operating-system account for each person; do not share this folder with other users.

Only visible messages are stored here, never hidden model reasoning. Original authorship/model identity is retained when you correct a message. Attachments are represented by IDs and authenticated hearth links; image/audio binaries and identity credentials are not part of this export. This ZIP is a text/history export, not a complete appliance backup. A shorter active chat context never removes the saved history.
'''


def dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str)


def markdown(metadata, content):
    # JSON scalars are valid YAML scalars, with no interpolation into YAML syntax.
    return '---\n' + '\n'.join(f'{key}: {dumps(value)}' for key, value in metadata.items()) + '\n---\n' + content


def parse_markdown(value):
    value = value.removeprefix('\ufeff').replace('\r\n', '\n')
    if not value.startswith('---\n'):
        if not value.strip() or len(value) > 6000:
            raise HTTPException(400, 'A new memory note must contain between 1 and 6,000 characters.')
        return {}, value.strip()
    head, marker, content = value[4:].partition('\n---\n')
    if not marker or len(head) > 4000:
        raise HTTPException(400, 'This file has incomplete or oversized frontmatter.')
    metadata = {}
    try:
        for line in head.splitlines():
            key, separator, raw = line.partition(':')
            if not separator or not re.fullmatch('[a-z_]+', key) or key in metadata:
                raise ValueError('invalid metadata')
            if raw.strip().startswith(('!', '&', '*')):
                raise ValueError('Tagged or aliased metadata is not supported')
            metadata[key] = yaml.safe_load(raw)
            if isinstance(metadata[key], (dict, list)):
                raise ValueError('Metadata must contain scalar properties')
        if metadata.get('schema') != 'hearth.memory.v1':
            raise ValueError('unsupported schema')
    except (ValueError, TypeError, yaml.YAMLError) as exc:
        raise HTTPException(400, 'Keep the exported hearth frontmatter intact. Edit the Markdown below it, or import a new note without frontmatter.') from exc
    return metadata, content


def snapshot(db, settings):
    from hearth.memory import source_current
    lineage = {}
    scope = {'schema': 'hearth.memory.v1', 'scope': str(settings['owner_id']), 'farm': str(settings['farm_id']), 'locality': 'local_only'}
    files = {'README.md': README}
    graph = {'schema': 'hearth.memory.graph.v1', 'scope': scope['scope'], 'farm': scope['farm'], 'nodes': [], 'edges': []}
    notes = [dict(row) for row in db.execute(text('SELECT * FROM memory_notes WHERE deleted_at IS NULL ORDER BY id')).mappings()]
    conversations = [dict(row) for row in db.execute(text("SELECT * FROM conversations WHERE kind='chat' ORDER BY id")).mappings()]
    lookup = {}
    for note in notes:
        node_id = str(note['id'])
        metadata = scope | {key: note[key] for key in ('id', 'revision', 'title', 'kind', 'enabled', 'created_at', 'updated_at')} | {'type': 'note'}
        files[f'notes/{node_id}.md'] = markdown(metadata, note['body'])
        if note['enabled']:
            graph['nodes'].append({'id': node_id, 'type': 'note', 'title': note['title'], 'path': f'notes/{node_id}.md'})
            lookup[node_id] = node_id
    for chat in conversations:
        chat_id = str(chat['id'])
        rows = [dict(row) for row in db.execute(text('''SELECT m.id,m.sequence,m.role,m.content,m.status,m.created_at,m.memory_revision AS revision,m.attachment_ids,
            r.route_receipt,r.memory_receipt FROM messages m LEFT JOIN chat_runs r ON r.assistant_message_id=m.id WHERE m.conversation_id=:id ORDER BY m.sequence'''), {'id': chat['id']}).mappings()]
        pieces, jsonl = [f"# {chat['title'].replace(chr(10), ' ')}\n\n"], []
        if not chat['memory_excluded']:
            graph['nodes'].append({'id': chat_id, 'type': 'conversation', 'title': chat['title'], 'path': f'conversations/{chat_id}.md'})
        for row in rows:
            source_id = str(row['id'])
            model = (row['route_receipt'] or {}).get('model_id')
            meta = scope | {key: row[key] for key in ('id', 'revision', 'sequence', 'role', 'status', 'created_at')} | {'type': 'message', 'conversation_id': chat_id, 'model_id': model}
            files[f'messages/{source_id}.md'] = markdown(meta, row['content'])
            # Body remains unmodified; complete exact source is also in JSONL.
            pieces.append(f"## {row['sequence']} · {'You' if row['role']=='user' else 'hearth'}\n\n[[messages/{source_id}|Open editable message]]\n\n{row['content']}\n\n")
            images = [str(item) for item in db.execute(text('SELECT id FROM conversation_images WHERE message_id=:id'), {'id': row['id']}).scalars()]
            jsonl.append(dumps(meta | {'content': row['content'], 'attachment_ids': row['attachment_ids'], 'image_ids': images, 'route_receipt': row['route_receipt'], 'memory_receipt': row['memory_receipt']}))
            if not chat['memory_excluded'] and row['status'] == 'completed' and source_current(db, {'type': 'message', 'id': row['id'], 'revision': row['revision']}, lineage, set()):
                graph['nodes'].append({'id': source_id, 'type': 'message', 'title': f"Message {row['sequence']}", 'path': f'messages/{source_id}.md'})
                graph['edges'].append({'source': chat_id, 'target': source_id, 'relation': 'contains', 'evidence': source_id})
                lookup[source_id] = source_id
        files[f'conversations/{chat_id}.md'] = markdown(scope | {'type': 'transcript', 'id': chat_id, 'revision': chat['revision'], 'excluded_from_recall': chat['memory_excluded'], 'archived': chat['deleted_at'] is not None}, ''.join(pieces))
        files[f'conversations/{chat_id}.jsonl'] = '\n'.join(jsonl) + '\n'
    # Native Obsidian links only. No inferred edges, model calls or cross-user traversal.
    for note in notes:
        if not note['enabled']:
            continue
        for target in set(re.findall(r'\[\[(?:notes/|messages/)?([0-9a-f-]{36})(?:\|[^\]]*)?\]\]', note['body'])):
            if target in lookup:
                graph['edges'].append({'source': str(note['id']), 'target': target, 'relation': 'links_to', 'evidence': str(note['id'])})
    revisions = []
    for table, kind in (('memory_note_revisions', 'note'), ('memory_message_revisions', 'message')):
        revisions.extend(dumps(dict(item) | {'type': kind}) for item in db.execute(text(f'SELECT * FROM {table} ORDER BY created_at')).mappings())
    files['revisions.jsonl'] = '\n'.join(revisions) + '\n'
    files['graph.json'] = dumps(graph)
    files['manifest.json'] = dumps(scope | {'generation': settings['generation'], 'files': {name: hashlib.sha256(content.encode('utf-8')).hexdigest() for name, content in files.items()}})
    return files


def zip_bytes(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return output.getvalue()


def project(engine, farm_id, owner_id, root):
    from hearth.memory import state
    # Paths never depend on filenames, titles or frontmatter supplied by a user.
    base = Path(root).resolve() / str(UUID(str(farm_id))) / str(UUID(str(owner_id)))
    with scoped_session(engine, owner_id, farm_id) as db:
        settings = state(db, lock=True)
        if settings['projected_generation'] >= settings['generation']:
            return False
        files = snapshot(db, settings)
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        manifest_path = base / 'manifest.json'
        previous = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {'files': {}}
        previous_hashes = previous.get('files', {})
        for name in sorted((set(files) | set(previous_hashes)) - {'manifest.json'}) + ['manifest.json']:
            # Previous manifests are disk data, not path authority.
            if name not in {'README.md', 'manifest.json', 'graph.json', 'revisions.jsonl'} and not re.fullmatch(r'(notes|messages|conversations)/[0-9a-f-]{36}\.(md|jsonl)', name):
                raise ValueError('Invalid vault manifest path')
            path = base / name
            if not path.resolve().is_relative_to(base) or path.is_symlink():
                raise ValueError('Invalid vault destination')
            expected = files.get(name)
            current = path.read_bytes() if path.exists() else None
            if current is not None and expected is not None and current == expected.encode('utf-8'):
                continue
            if current is not None and name != 'manifest.json' and hashlib.sha256(current).hexdigest() != previous_hashes.get(name):
                conflict = base / 'conflicts'
                if conflict.is_symlink() or not conflict.resolve().is_relative_to(base):
                    raise ValueError('Invalid conflict destination')
                conflict.mkdir(exist_ok=True, mode=0o700)
                (conflict / f'{uuid4()}.md').write_bytes(current)
            if expected is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                temporary = path.with_name(f'.{uuid4()}.tmp')
                try:
                    temporary.write_text(expected, encoding='utf-8', newline='')
                    temporary.chmod(0o600)
                    os.replace(temporary, path)
                finally:
                    temporary.unlink(missing_ok=True)
        db.execute(text('UPDATE memory_settings SET projected_generation=:generation,projected_at=now(),projection_error=NULL'), {'generation': settings['generation']})
        db.execute(text("UPDATE outbox SET delivered_at=now() WHERE event_type='memory.vault.changed' AND aggregate_version<=:generation AND delivered_at IS NULL"), {'generation': settings['generation']})
    return True


class VaultProjector:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, name='hearth-private-vaults', daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                with self.engine.connect() as db:
                    owners = db.execute(text("SELECT id FROM users WHERE farm_id=:farm AND state='active'"), {'farm': self.settings.farm_id}).scalars().all()
                for owner in owners:
                    if self.stop.is_set():
                        break
                    try:
                        # An administrator account without a personal workspace has nothing to project.
                        with scoped_session(self.engine, owner, self.settings.farm_id) as db:
                            exists = db.execute(text('SELECT id FROM workspaces')).first()
                        if exists:
                            project(self.engine, self.settings.farm_id, owner, self.settings.memory_vault_path)
                    except Exception:
                        with scoped_session(self.engine, owner, self.settings.farm_id) as db:
                            db.execute(text("UPDATE memory_settings SET projection_error='Vault copy unavailable. Your committed history is safe in the database; projection will retry.'"))
            except Exception:
                # Do not leak private content, filesystem paths or credentials to logs.
                pass
            self.stop.wait(10)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=15)
