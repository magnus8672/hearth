"""Render an exported private explicit-link graph with pinned Graphify, fully offline.

Usage: uv run --group knowledge python scripts/graphify_vault.py PATH/graph.json NEW_OUTPUT_DIR
This does not invoke Graphify's semantic extraction CLI or any model/provider.
"""
import argparse
import json
from importlib.metadata import version
from pathlib import Path
from uuid import UUID


def render(graph, output):
    from graphify.build import build_from_json
    from graphify.export import to_obsidian
    if version('graphifyy') != '0.1.14':
        raise ValueError('Use the locked hearth knowledge dependency: graphifyy 0.1.14.')
    if graph.get('schema') != 'hearth.memory.graph.v1':
        raise ValueError('Expected a scoped hearth graph export.')
    UUID(graph['scope'])
    UUID(graph['farm'])
    nodes, edges, ids = [], [], set()
    folders = {'note': 'notes', 'message': 'messages', 'conversation': 'conversations'}
    for node in graph['nodes']:
        key = str(UUID(node['id']))
        if node['id'] != key or key in ids or node['type'] not in folders:
            raise ValueError('Invalid or duplicate node.')
        path = f"{folders[node['type']]}/{key}.md"
        if node['path'] != path:
            raise ValueError('Graph nodes must refer to an opaque file in this vault.')
        ids.add(key)
        # Upstream embeds these values into filenames and frontmatter. Only use
        # validated IDs and generated metadata, never user-authored labels.
        nodes.append({'id': key, 'label': key, 'file_type': 'document', 'source_file': path})
    for edge in graph['edges']:
        if any(edge[key] not in ids for key in ('source', 'target', 'evidence')) or edge['relation'] not in {'contains', 'links_to'}:
            raise ValueError('Every edge must have source evidence inside this scoped export.')
        edges.append({key: edge[key] for key in ('source', 'target', 'relation')} | {'confidence': 'EXTRACTED'})
    target = Path(output)
    if target.exists():
        raise ValueError('Choose a new output directory; existing files are never overwritten.')
    target.mkdir(parents=True, mode=0o700)
    model = build_from_json({'nodes': nodes, 'edges': edges})
    count = to_obsidian(model, {}, str(target))
    (target / 'README.md').write_text('''# hearth graph

Generated offline by Graphify 0.1.14 from explicit links in one private vault.
Node names are stable source IDs. Their source_file property points back to the
exported note, message, or transcript. This is a derived graph, not semantic
extraction, synchronization, or a new source of truth. Rebuild into a new folder
after corrections, exclusions, or removals. Never merge different users' graphs.
''', encoding='utf-8')
    return {'nodes': len(nodes), 'edges': len(edges), 'notes_written': count, 'network_calls': 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('graph', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(render(json.loads(args.graph.read_text(encoding='utf-8')), args.output)))


if __name__ == '__main__':
    main()
