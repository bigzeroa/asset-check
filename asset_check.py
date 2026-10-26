"""Read-only asset preflight: duplicates, image formats, dimensions and portable names."""
from __future__ import annotations
import argparse,hashlib,html,json,os,re,stat,sys,warnings
from collections import defaultdict
from pathlib import Path
from PIL import Image,UnidentifiedImageError

IMAGE_EXT={'.png':'PNG','.jpg':'JPEG','.jpeg':'JPEG','.webp':'WEBP','.gif':'GIF','.bmp':'BMP','.tif':'TIFF','.tiff':'TIFF','.tga':'TGA','.dds':'DDS','.ico':'ICO','.psd':'PSD'}
IGNORED={'.git','.godot','node_modules','.venv','__pycache__','library','temp','obj'}

def reparse(path):
    info=path.stat(follow_symlinks=False)
    return path.is_symlink() or bool(getattr(info,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024))

def name_problems(relative):
    problems=[]
    for part in relative.split('/'):
        if re.search(r'[<>:"|?*\x00-\x1f]',part):problems.append('Windows-incompatible characters')
        if part.endswith((' ','.')):problems.append('trailing space or dot')
        if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',part.split('.')[0],re.I):problems.append('reserved Windows name')
    return sorted(set(problems))

def scan(root,*,max_dimension=2048,max_file_bytes=256*1024*1024,max_files=20000,max_image_pixels=32*1024*1024,pixel_duplicates=False,require_power_of_two=False):
    root=Path(root)
    if reparse(root):raise ValueError('The scan root cannot be a symbolic link or junction.')
    root=root.resolve()
    if not root.is_dir():raise ValueError('Choose an existing asset directory.')
    if min(max_dimension,max_file_bytes,max_files,max_image_pixels)<1:raise ValueError('Limits must be positive.')
    report={'format':'asset-check/v1','rootName':root.name,'policy':{'maxDimension':max_dimension,'maxFileBytes':max_file_bytes,'maxFiles':max_files,'maxImagePixels':max_image_pixels,'pixelDuplicates':pixel_duplicates,'requirePowerOfTwo':require_power_of_two},'files':[],'issues':[],'duplicateGroups':[],'skipped':[]}
    byte_groups=defaultdict(list);pixel_groups=defaultdict(list);case_groups=defaultdict(list);incomplete=False;stopped=False
    def issue(code,path,message,severity='warning'):
        report['issues'].append({'code':code,'path':path,'severity':severity,'message':message})
    def skip(path,reason,partial=False):
        nonlocal incomplete
        report['skipped'].append({'path':path,'reason':reason});incomplete=incomplete or partial
    def traversal_error(error):
        nonlocal incomplete
        incomplete=True;issue('unreadable_directory','(directory)','A directory could not be read: '+str(error.strerror),'error')
    for directory,dirs,names in os.walk(root,topdown=True,followlinks=False,onerror=traversal_error):
        keep=[]
        for name in sorted(dirs):
            path=Path(directory)/name;relative=path.relative_to(root).as_posix()
            try:
                if name.casefold() in IGNORED:skip(relative,'ignored generated/version-control directory')
                elif reparse(path):skip(relative,'symlink or junction not followed')
                else:keep.append(name)
            except OSError:skip(relative,'directory metadata unavailable',True)
        dirs[:]=keep
        for name in sorted(names):
            path=Path(directory)/name;relative=path.relative_to(root).as_posix()
            if len(report['files'])>=max_files:
                issue('file_limit','(scan)','File limit reached; remaining files were not scanned.');incomplete=True;stopped=True;break
            try:
                if reparse(path):skip(relative,'symlink or reparse point not followed');continue
                before=path.stat()
                if not stat.S_ISREG(before.st_mode):skip(relative,'not a regular file');continue
                item={'path':relative,'bytes':before.st_size};report['files'].append(item);case_groups[relative.casefold()].append(relative)
                for problem in name_problems(relative):issue('nonportable_name',relative,problem+'. Review before importing on another platform.')
                if before.st_size>max_file_bytes:
                    skip(relative,'file exceeds configured byte limit',True);continue
                digest=hashlib.sha256()
                with path.open('rb') as stream:
                    header=stream.read(32);digest.update(header)
                    for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
                after=path.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                    issue('changed_during_scan',relative,'File changed while it was read; no duplicate match was recorded.','error');incomplete=True;continue
                item['sha256']=digest.hexdigest();byte_groups[(before.st_size,item['sha256'])].append(relative)
                expected=IMAGE_EXT.get(path.suffix.lower())
                looks_image=(header.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff',b'GIF87a',b'GIF89a',b'BM',b'II*\x00',b'MM\x00*',b'\x00\x00\x01\x00',b'DDS ',b'8BPS')) or (header[:4]==b'RIFF' and header[8:12]==b'WEBP'))
                if expected or looks_image:
                    try:
                        with warnings.catch_warnings():
                            warnings.simplefilter('error',Image.DecompressionBombWarning)
                            with Image.open(path) as image:
                                actual=image.format;w,h=image.size;frames=getattr(image,'n_frames',1)
                                item.update({'imageFormat':actual,'width':w,'height':h,'frames':frames})
                                if actual!=expected:issue('extension_mismatch',relative,f'Content is {actual}; filename extension is {path.suffix or "(none)"}. Renaming alone does not convert a file.')
                                if max(w,h)>max_dimension:issue('oversized_texture',relative,f'{w} x {h} exceeds the configured {max_dimension}px review threshold; this is not a universal engine limit.')
                                if require_power_of_two and (w&(w-1) or h&(h-1)):issue('non_power_of_two',relative,f'{w} x {h} is not power-of-two. This is an opt-in project policy, not always an error.')
                                if w*h>max_image_pixels:
                                    skip(relative,'image decode exceeds pixel budget; dimensions only',True);continue
                                image.verify()
                            with Image.open(path) as image:
                                image.seek(0);image.load()
                                if pixel_duplicates and frames==1:
                                    rgba=image.convert('RGBA');pixel_hash=hashlib.sha256(rgba.tobytes()).hexdigest();rgba.close()
                                    item['pixelSha256']=pixel_hash;pixel_groups[(w,h,pixel_hash)].append(relative)
                                elif frames>1:skip(relative,'only first frame decoded; no animated-image pixel matching')
                    except (Image.DecompressionBombError,Image.DecompressionBombWarning):
                        skip(relative,'Pillow decompression safety limit; no pixel decode',True)
                    except (OSError,ValueError,SyntaxError,UnidentifiedImageError) as error:
                        message=str(error).replace(repr(str(path)),repr(relative)).replace(str(path),relative)
                        issue('unreadable_image',relative,'Image could not be verified or decoded: '+message,'error')
            except OSError as error:
                issue('unreadable_file',relative,'File could not be read: '+str(error.strerror),'error');incomplete=True
        if stopped:break
    for paths in case_groups.values():
        if len(paths)>1:issue('case_collision',paths[0],'Paths may collide on case-insensitive systems: '+', '.join(paths))
    for kind,groups in [('byte-identical',byte_groups),('decoded-rgba-identical',pixel_groups)]:
        for paths in groups.values():
            if len(paths)<2:continue
            # Pixel groups already covered by one byte group add no new information.
            if kind=='decoded-rgba-identical' and any(set(paths)<=set(group) for group in byte_groups.values()):continue
            report['duplicateGroups'].append({'kind':kind,'paths':paths})
            issue('duplicate_'+('bytes' if kind=='byte-identical' else 'pixels'),paths[0],f'{len(paths)} {kind} files. Review references before removing anything.')
    report['summary']={'scannedFiles':len(report['files']),'scannedBytes':sum(f['bytes'] for f in report['files']),'images':sum('imageFormat' in f for f in report['files']),'errors':sum(i['severity']=='error' for i in report['issues']),'warnings':sum(i['severity']=='warning' for i in report['issues']),'duplicateGroups':len(report['duplicateGroups']),'skippedChecks':len(report['skipped']),'incomplete':incomplete}
    return report

def render_html(report):
    e=lambda value:html.escape(str(value),quote=True)
    rows=''.join('<tr><td>'+e(i['severity'])+'</td><td><code>'+e(i['path'])+'</code></td><td>'+e(i['code'])+'</td><td>'+e(i['message'])+'</td></tr>' for i in report['issues'])
    groups=''.join('<li>'+e(g['kind'])+'<ul>'+''.join('<li><code>'+e(p)+'</code></li>' for p in g['paths'])+'</ul></li>' for g in report['duplicateGroups'])
    skips=''.join('<li><code>'+e(s['path'])+'</code>: '+e(s['reason'])+'</li>' for s in report['skipped'])
    s=report['summary']
    return '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Asset Check report</title><style>body{font:16px/1.6 system-ui;background:#f1f4f7;color:#172b42;max-width:1100px;margin:40px auto;padding:0 20px}table{border-collapse:collapse;width:100%;background:white}td,th{padding:12px;border:1px solid #cbd5e1;text-align:left;vertical-align:top}code{overflow-wrap:anywhere}a{color:#185ad9}</style><h1>Asset Check</h1><p>Directory: '+e(report['rootName'])+'</p><p>'+e(s['scannedFiles'])+' files; '+e(s['errors'])+' errors; '+e(s['warnings'])+' warnings. '+('Scan incomplete: review skipped checks.' if s['incomplete'] else 'Configured scan completed.')+'</p><p>Read-only report. No source files were deleted, renamed, moved or rewritten. A duplicate may be intentionally referenced by your project.</p><h2>Findings</h2><table><thead><tr><th>Level</th><th>File</th><th>Check</th><th>Details</th></tr></thead><tbody>'+rows+'</tbody></table><h2>Duplicate groups</h2><ul>'+groups+'</ul><h2>Skipped checks</h2><ul>'+skips+'</ul></html>'

def render_text(report):
    s=report['summary'];lines=[f"Asset Check: {report['rootName']}",f"{s['scannedFiles']} files / {s['errors']} errors / {s['warnings']} warnings"]
    lines += [f"[{i['severity']}] {i['path']}: {i['code']} — {i['message']}" for i in report['issues']]
    lines += [f"[skipped] {i['path']}: {i['reason']}" for i in report['skipped']]
    if s['incomplete']:lines.append('INCOMPLETE: review skipped checks or raise explicit scan limits.')
    return '\n'.join(lines)+'\n'

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--format',choices=['text','json','html'],default='text')
    parser.add_argument('-o','--output',type=Path,help='Optional NEW report path outside the scanned directory. Default: stdout.')
    parser.add_argument('--max-dimension',type=int,default=2048)
    parser.add_argument('--max-file-mb',type=int,default=256)
    parser.add_argument('--max-files',type=int,default=20000)
    parser.add_argument('--max-image-mp',type=int,default=32)
    parser.add_argument('--pixel-duplicates',action='store_true')
    parser.add_argument('--require-power-of-two',action='store_true')
    parser.add_argument('--fail-on',choices=['error','warning','never'],default='error')
    args=parser.parse_args(argv)
    try:
        if args.output:
            output=args.output.resolve();root=args.directory.resolve()
            if output==root or root in output.parents:raise ValueError('Write reports outside the scanned directory so source assets remain untouched.')
            if output.exists():raise ValueError('Report already exists. Choose a new name; reports are never overwritten.')
        report=scan(args.directory,max_dimension=args.max_dimension,max_file_bytes=args.max_file_mb*1024*1024,max_files=args.max_files,max_image_pixels=args.max_image_mp*1024*1024,pixel_duplicates=args.pixel_duplicates,require_power_of_two=args.require_power_of_two)
        result=json.dumps(report,indent=2,ensure_ascii=False)+'\n' if args.format=='json' else render_html(report) if args.format=='html' else render_text(report)
        if args.output:
            # The caller explicitly selected this new report, outside the scan root.
            with args.output.open('x',encoding='utf-8') as f:f.write(result)
        else:
            if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
            sys.stdout.write(result)
    except (ValueError,OSError) as error:parser.error(str(error))
    if report['summary']['incomplete']:return 2
    if args.fail_on=='never':return 0
    return int(report['summary']['errors']>0 or (args.fail_on=='warning' and report['summary']['warnings']>0))

if __name__=='__main__':raise SystemExit(main())
