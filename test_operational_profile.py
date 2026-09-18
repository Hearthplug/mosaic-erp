import tempfile,unittest
from store import Store
from operational_profile import Profiles
class ProfilesTest(unittest.TestCase):
 def test_interview_applies_working_module_profile(self):
  s=Store(tempfile.mktemp());w,_=s.create_workspace('Retail');p=Profiles(s).apply(w,'owner',{'vertical':'Electronics','locations':'2–5 stores','credit':'Customer credit','country':'India'});self.assertTrue({'service','serials','transfers','receivables'}<=set(p['enabled_modules']));row=s._db.execute('SELECT operational_profile_hash FROM workspaces WHERE id=?',(w,)).fetchone();self.assertTrue(row['operational_profile_hash'])
if __name__=='__main__':unittest.main()
