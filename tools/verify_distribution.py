"""Check the root installer and optionally test direct ISO construction."""
import argparse, json, shutil, subprocess, sys, tempfile
from pathlib import Path
from project import ROOT, cfg, dump, verify_iso, audit, build_image, digest

INSTALLER_FILES = {'install.cmd', 'project.json', 'tools/project.py',
    'resources/manifest.json', 'reference/english_v3_inventory.json'}

def validate_installer(c):
    assert all((ROOT/path).is_file() for path in INSTALLER_FILES)
    assert not any((ROOT/name).exists() for name in ['apply.py','package.json','patch.json.gz'])

def run(source=None,full_install=False,report=None):
    c=cfg();validate_installer(c);direct_build=None
    if source:
        build_image(source);direct_build=True
    else:audit()
    result=dict(status='passed',installer_files=sorted(INSTALLER_FILES),installer_verified=True,
        direct_build_verified=direct_build,iso_written=False,full_installation='not_run')
    if full_install:
        assert source,'--input is required with --full-install'
        with tempfile.TemporaryDirectory(prefix='socom-package-test-') as directory:
            test=Path(directory).resolve()
            # Restrict both test writes and automatic recursive cleanup to this fresh directory.
            assert test.name.startswith('socom-package-test-')
            extracted=test/'repository';extracted.mkdir()
            for name in ['tools','resources','reference']:shutil.copytree(ROOT/name,extracted/name)
            for name in ['install.cmd','project.json']:shutil.copy2(ROOT/name,extracted/name)
            output=test/'translated.iso';source=Path(source).expanduser().resolve()
            fake=test/'wrong.iso';fake.write_bytes(b'not an ISO')
            def install(base):
                return subprocess.run([sys.executable,'-B',str(extracted/'tools/project.py'),'build','--input',str(base),
                    '--output',str(output)],cwd=test,capture_output=True,text=True)
            bad=install(fake)
            assert bad.returncode!=0 and not output.exists() and not output.with_name(output.name+'.partial').exists()
            installed=install(source)
            assert installed.returncode==0,(installed.stdout,installed.stderr)
            assert digest(output)==c['current']['sha256']
            repeat=install(source)
            assert repeat.returncode!=0 and digest(output)==c['current']['sha256']
            manifest,inv=audit();result.update(verify_iso(output,manifest,inv))
            result.update(full_installation='passed',iso_written=True,wrong_input_rejected=True,existing_output_preserved=True)
        assert not test.exists()
        result['temporary_files_removed']=True
    if report:dump(Path(report).expanduser().resolve(),result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',help='Clean English USA v3.00 ISO; enables direct-build verification')
    parser.add_argument('--full-install',action='store_true',help='Create and verify a temporary ISO; requires about 3.5 GB free')
    parser.add_argument('--report',help='Optional JSON report path')
    args=parser.parse_args();run(args.input,args.full_install,args.report)
