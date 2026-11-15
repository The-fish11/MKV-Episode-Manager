import hashlib,json,os,re,shutil,subprocess,tempfile,time
from pathlib import Path

MODES=('Complete TV Season','Incomplete TV Season','Movie')
BAD=re.compile(r'[<>:"/\\|?*\x00-\x1f]')
def clean(s):return BAD.sub('_',str(s)).strip(' .')[:170]
def suggest(item,mode,series,season):
    if mode=='Movie':
        title=clean(item.get('title') or series);year=str(item.get('year') or '').strip()
        return f'{title} ({year}).mkv' if title and re.fullmatch(r'\d{4}',year) else (f'{title}.mkv' if title else '')
    try: n=int(item.get('episode')); s=int(season)
    except (ValueError,TypeError):return ''
    if n<1 or s<0 or not clean(series):return ''
    title=clean(item.get('title') or '')
    return f'{clean(series)} - S{s:02d}E{n:02d}'+(f' - {title}' if title else '')+'.mkv'
def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def validate_destination(paths,destination):
    d=Path(destination)
    if d.is_symlink() or not d.is_dir():raise ValueError('Select an existing, non-symlink output directory')
    d=d.resolve(strict=True)
    if not paths:raise ValueError('No sources')
    sources=[Path(p) for p in paths]
    if any(p.is_symlink() or not p.is_file() for p in sources):raise ValueError('Source missing or symlinked')
    sources=[p.resolve(strict=True) for p in sources]
    common=Path(os.path.commonpath([str(p.parent) for p in sources]))
    if d==common or common in d.parents or d in common.parents:raise ValueError('Output must be separate from the source tree')
    return d
def verified_copy(src,directory,name):
    source=Path(src)
    if source.is_symlink() or not source.is_file():raise ValueError('Invalid source')
    source=source.resolve(strict=True)
    directory=Path(directory).resolve(strict=True)
    if name!=clean(name) or not name.lower().endswith('.mkv') or not name:raise ValueError('Invalid filename')
    target=directory/name;partial=directory/(name+'.part')
    if target.exists() or target.is_symlink():raise FileExistsError(str(target))
    with open(source,'rb') as inp,open(partial,'xb') as out:
        shutil.copyfileobj(inp,out,4*1024*1024);out.flush();os.fsync(out.fileno())
    a=digest(source);b=digest(partial)
    if a!=b:raise IOError('SHA-256 mismatch; .part retained')
    # Link is an atomic, no-overwrite destination claim on the same filesystem.
    os.link(partial,target);partial.unlink()
    return {'source':str(source),'destination':str(target),'sha256':a,'verified':True}
def inspect(path):
    data={'size_bytes':Path(path).stat().st_size}
    try:
        p=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,text=True,timeout=35,check=True)
        obj=json.loads(p.stdout);streams=obj.get('streams',[]);v=next((s for s in streams if s.get('codec_type')=='video'),{})
        data.update(codec=v.get('codec_name'),width=v.get('width'),height=v.get('height'),duration=round(float(obj.get('format',{}).get('duration',0)),1),audio=sum(s.get('codec_type')=='audio' for s in streams),subtitles=sum(s.get('codec_type')=='subtitle' for s in streams))
    except Exception as e:data['error']=str(e)
    return data
def frames(path,folder,count=6):
    """Frames from relative timestamps; no modification of source."""
    info=inspect(path);duration=info.get('duration',0);result=[]
    if duration<=0:raise RuntimeError('FFprobe could not read video duration')
    for i in range(count):
        at=max(1,duration*(i+1)/(count+1));out=Path(folder)/f'frame_{i:02}.jpg'
        p=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-nostdin','-ss',str(at),'-i',str(path),'-frames:v','1','-y',str(out)],capture_output=True,text=True,timeout=45)
        if p.returncode==0 and out.exists():result.append((str(out),int(at)))
    if not result:raise RuntimeError('FFmpeg could not extract any frames')
    return result

def save(path,data):
    dest=Path(path);dest.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.mkv_',suffix='.tmp',dir=dest.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:json.dump({'version':'0.4.1',**data},f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(tmp,dest)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
