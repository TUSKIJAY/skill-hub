import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec=importlib.util.spec_from_file_location('hub',Path(__file__).resolve().parents[1]/'scripts/hub.py')
hub=importlib.util.module_from_spec(spec);spec.loader.exec_module(hub)

class HubTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name);self.root=self.base/'repo';self.home=self.base/'home'
        self.src=self.root/'skills/example';self.src.mkdir(parents=True)
        self.file=self.src/'SKILL.md';self.file.write_text('---\nname: example\ndescription: Example skill\n---\nShort instructions.\n')
        hub.write(self.root/'catalog.json',{'version':1,'skills':[{'id':'example','title':'Example','summary':'Example','category':'test','kind':'managed','path':'skills/example','origin':{'kind':'test'}}]})
        hub.write(self.root/'profiles.json',{'test':['example']})
        self.dst=hub.target(self.home,'codex','example')
    def tearDown(self):self.tmp.cleanup()
    def test_directory_not_overwritten_by_default(self):
        self.dst.mkdir(parents=True);(self.dst/'mine').write_text('keep')
        with self.assertRaisesRegex(ValueError,'preserved'):hub.install(self.root,self.home,'example','codex')
        self.assertEqual((self.dst/'mine').read_text(),'keep')
    def test_replace_and_restore(self):
        self.dst.mkdir(parents=True);(self.dst/'mine').write_text('keep')
        hub.install(self.root,self.home,'example','codex',replace=True)
        self.assertTrue(self.dst.is_symlink())
        hub.uninstall(self.root,self.home,'codex','example',restore_previous=True)
        self.assertFalse(self.dst.is_symlink());self.assertEqual((self.dst/'mine').read_text(),'keep')
    def test_dry_run_no_state_or_install(self):
        hub.install(self.root,self.home,'example','codex',dry_run=True)
        self.assertFalse(self.dst.exists());self.assertFalse(hub.state_path(self.root).exists())
    def test_repeat_link_install(self):
        hub.install(self.root,self.home,'example','codex')
        self.assertEqual(hub.install(self.root,self.home,'example','codex')['status'],'already-current')
    def test_agents_link_directly_to_hub(self):
        hub.install(self.root,self.home,'example','codex')
        other=hub.target(self.home,'claude','example');other.parent.mkdir(parents=True);other.symlink_to(self.dst)
        hub.install(self.root,self.home,'example','claude',replace=True)
        self.assertEqual(other.readlink(),self.src.resolve())
    def test_copy_update_preserves_user_changes(self):
        hub.install(self.root,self.home,'example','codex',mode='copy')
        (self.dst/'SKILL.md').write_text('my edits');self.file.write_text('new upstream')
        with self.assertRaisesRegex(ValueError,'locally-modified'):hub.update(self.root,self.home,'codex','example')
        self.assertEqual((self.dst/'SKILL.md').read_text(),'my edits')
    def test_copy_updates_to_new_source(self):
        hub.install(self.root,self.home,'example','codex',mode='copy');self.file.write_text('new upstream')
        self.assertEqual(hub.inspect_install(self.root,self.home,'codex','example')['status'],'update-available')
        hub.update(self.root,self.home,'codex','example');self.assertEqual((self.dst/'SKILL.md').read_text(),'new upstream')
    def test_replaced_link_not_uninstalled(self):
        hub.install(self.root,self.home,'example','codex');self.dst.unlink();self.dst.mkdir();(self.dst/'other').write_text('keep')
        with self.assertRaisesRegex(ValueError,'replaced-locally'):hub.uninstall(self.root,self.home,'codex','example')
    def test_atomic_install_failure_restores_prior(self):
        self.dst.mkdir(parents=True);(self.dst/'mine').write_text('keep');original=hub.os.replace
        def fail(source,dest):
            if Path(dest)==self.dst:raise OSError('simulated failure')
            return original(source,dest)
        with patch.object(hub.os,'replace',side_effect=fail):
            with self.assertRaises(OSError):hub.install(self.root,self.home,'example','codex',replace=True)
        self.assertEqual((self.dst/'mine').read_text(),'keep')
    def test_reference_not_installable(self):
        d=hub.read(self.root/'catalog.json');d['skills'][0]['kind']='reference';hub.write(self.root/'catalog.json',d)
        with self.assertRaisesRegex(ValueError,'reference only'):hub.install(self.root,self.home,'example','codex')
    def test_source_escape_rejected(self):
        d=hub.read(self.root/'catalog.json');d['skills'][0]['path']='../outside';hub.write(self.root/'catalog.json',d)
        with self.assertRaisesRegex(ValueError,'escapes'):hub.registry(self.root)
    def test_secret_scan_does_not_echo_secret(self):
        fake='ghp_'+'a'*30;self.file.write_text(self.file.read_text()+fake)
        with self.assertRaises(ValueError) as caught:hub.validate(self.root)
        self.assertNotIn(fake,str(caught.exception));self.assertIn('possible secret',str(caught.exception))
    def test_metadata_does_not_load_skill_instructions(self):
        original=Path.read_text;seen=[]
        def read(path,*args,**kwargs):seen.append(path);return original(path,*args,**kwargs)
        with patch.object(Path,'read_text',read):hub.registry(self.root)
        self.assertEqual(seen,[self.root/'catalog.json'])
    def test_link_tracks_shared_source(self):
        hub.install(self.root,self.home,'example','codex');self.file.write_text('new text')
        self.assertEqual((self.dst/'SKILL.md').read_text(),'new text')
        self.assertEqual(hub.inspect_install(self.root,self.home,'codex','example')['status'],'current')
    def test_internal_symlink_rejected(self):
        (self.src/'outside').symlink_to(self.base)
        with self.assertRaisesRegex(ValueError,'symlinks'):hub.install(self.root,self.home,'example','codex')

    def retire_example(self):
        d=hub.read(self.root/'catalog.json');d['skills'][0]['lifecycle']='retired';hub.write(self.root/'catalog.json',d)
    def test_retired_skill_cannot_install(self):
        self.retire_example()
        with self.assertRaisesRegex(ValueError,'retired'):hub.install(self.root,self.home,'example','codex')
        self.assertFalse(self.dst.exists())
    def test_all_excludes_retired(self):
        self.retire_example()
        with self.assertRaisesRegex(ValueError,'Choose a skill'):
            hub.selected_names(self.root,SimpleNamespace(names=[],profile=None,all=True))
    def test_profile_rejects_retired(self):
        self.retire_example()
        with self.assertRaisesRegex(ValueError,'Profile test: unavailable example'):hub.validate(self.root)
    def test_retired_skill_remains_discoverable(self):
        self.retire_example()
        self.assertEqual(hub.find(self.root,'example')['lifecycle'],'retired')
        self.assertTrue(self.file.exists())

if __name__=='__main__':unittest.main()
