import copy
import unittest
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('audit',Path(__file__).resolve().parents[1]/'scripts/audit_preflight.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)

class PreflightTests(unittest.TestCase):
 def setUp(self):
  self.before={'id':4736,'link':'https://unionnewsms.com/existing/','status':'publish',
   **{k:{'raw':'before','rendered':'before'} for k in ('content','title','excerpt')}}
  self.target={'id':4736,'link':self.before['link'],'rendered_sha256':{k:audit.digest('before') for k in ('content','title','excerpt')},
   'replacements':{'content':[{'old':'before','new':'after'}]}}
 def test_exact_minimal_payload_and_input_unchanged(self):
  saved=copy.deepcopy(self.before);self.assertEqual(audit.proposed(self.before,self.target),{'content':'after'});self.assertEqual(saved,self.before)
 def test_stale_article_rejected(self):
  self.before['content']['rendered']='changed'
  with self.assertRaises(ValueError):audit.proposed(self.before,self.target)
 def test_identity_and_status_rejected(self):
  for key,value in [('id',7),('link','https://other.example/'),('status','draft')]:
   changed=copy.deepcopy(self.before);changed[key]=value
   with self.assertRaises(ValueError):audit.proposed(changed,self.target)
 def test_wrong_occurrence_rejected(self):
  self.before['content']['raw']='beforebefore'
  with self.assertRaises(ValueError):audit.proposed(self.before,self.target)
 def test_slug_status_media_rejected(self):
  for key in ('slug','status','featured_media','date'):
   changed=copy.deepcopy(self.target);changed['set']={key:'other'}
   with self.assertRaises(ValueError):audit.proposed(self.before,changed)
 def test_metadata_scope_rejected(self):
  self.target['meta_replacements']={'private_field':[]}
  with self.assertRaises(ValueError):audit.proposed(self.before,self.target)
 def test_no_write_or_apply_route(self):
  source=Path(audit.__file__).read_text();self.assertNotIn("method='POST'",source);self.assertNotIn('--apply',source)

if __name__=='__main__':unittest.main()
