"""TMDB v3 API adapter. API key only used in request header, never saved to project."""
import json,re,urllib.parse,urllib.request
BASE='https://api.themoviedb.org/3'
class TMDB:
    def __init__(self,key):
        self.key=key.strip()
        if not self.key:raise ValueError('Enter your TMDB API Read Access Token or API key')
    def get(self,path,params=None):
        url=BASE+path+'?'+urllib.parse.urlencode({'language':'en-AU',**(params or {})})
        headers={'Accept':'application/json','User-Agent':'MKVEpisodeManager/0.4.1'}
        if self.key.startswith('eyJ'):headers['Authorization']='Bearer '+self.key
        else:
            url+='&api_key='+urllib.parse.quote(self.key)
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=15) as r:return json.load(r)
        except Exception as e:
            # Avoid exposing URLs, which may contain an API key.
            raise RuntimeError('TMDB request failed. Check internet access and your TMDB credentials.') from None
    def search(self,query,kind):return self.get('/search/'+kind,{'query':query,'include_adult':'false'}).get('results',[])[:15]
    def season(self,series_id,number):return self.get(f'/tv/{int(series_id)}/season/{int(number)}').get('episodes',[])
    def details(self,kind,id):return self.get(f'/{kind}/{int(id)}')
def guess_title(filename):
    stem=re.sub(r'(?i)([_ .-]*(?:disc|disk|dvd|bluray|blu-ray|bd|title|t)\s*\d+)+$','',filename.rsplit('.',1)[0])
    stem=re.sub(r'(?i)[-_. ]+t\d{2,3}$','',stem)
    stem=re.sub(r'[_]+',' ',stem).strip(' -_.')
    return stem
