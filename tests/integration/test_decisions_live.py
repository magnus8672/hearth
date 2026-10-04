"""Explicitly enabled CPU checkpoint qualification using disposable PostgreSQL identities."""
import os
from pathlib import Path
from uuid import uuid4

import pytest

from tests.integration.test_chat import csrf, promote
from tests.integration.test_decisions import wait
from tests.integration.test_identity import bff as bff
from tests.integration.test_identity import signin
from tests.integration.test_postgres import databases as databases


@pytest.mark.skipif(not os.environ.get('HEARTH_TEST_DECISION_SOCKET'), reason='Explicit isolated decision runtime required')
def test_real_typed_checkpoint_through_private_and_dedicated_http_apis(bff):
    factory, settings, _, migration, _ = bff
    settings.decision_socket = os.environ['HEARTH_TEST_DECISION_SOCKET']
    with factory('admin') as admin, factory() as user:
        signin(admin)
        promote(admin, migration, settings)
        headers = csrf(admin, settings.admin_origin)
        result = admin.post('/api/v1/providers', headers=headers, json={'name':'Dedicated decision qualification',
            'base_url':os.environ['HEARTH_TEST_DECISION_URL'], 'model_id':'convaiinnovations/laya-typed-decisions',
            'protocol':'hearth.decision.v1','local_only':True,'allow_insecure_http':True,
            'api_key':Path(os.environ['HEARTH_TEST_DECISION_TOKEN_FILE']).read_text().strip()})
        assert result.status_code == 201, result.text
        target = result.json()
        checked = admin.post('/api/v1/providers/'+target['id']+'/probe', headers=headers, json={'revision':target['revision']})
        assert checked.status_code == 200 and checked.json()['state'] == 'ready', checked.text
        signin(user)
        headers = csrf(user, settings.user_origin)
        questions = [
            {'id':'day','kind':'choice','instructions':'When did the parcel arrive?','options':{'monday':'Monday','friday':'Friday'}},
            {'id':'satisfaction','kind':'score','instructions':'How satisfied is the customer?','rubric':['Unhappy','Neutral','Delighted']},
            {'id':'delivered','kind':'boolean','instructions':'Has the parcel arrived?'},
        ]
        provenance = []
        for target_id in [None, target['id']]:
            data = {'id':str(uuid4()),'state':'The parcel arrived on Monday. The customer is delighted.','questions':questions,'target_id':target_id}
            submitted = user.post('/api/v1/decisions', headers=headers, json=data)
            assert submitted.status_code == 202, submitted.text
            outcome = wait(user,'/api/v1/decisions/'+data['id'])
            assert outcome['state'] == 'completed', outcome
            assert [q['kind'] for q in outcome['result']['answers']] == ['choice','score','boolean']
            assert outcome['result']['answers'][0]['choice'] == 'monday'
            assert not outcome['result']['truncated']
            provenance.append(outcome['receipt']['source'])
            assert user.delete('/api/v1/decisions/'+data['id'],headers=headers).status_code == 200
        assert provenance == ['builtin','dedicated']
