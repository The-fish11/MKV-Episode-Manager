import json,os,re,sys,tempfile,urllib.request
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal,QSize
from PySide6.QtGui import QPixmap,QIcon
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,QComboBox,QSpinBox,QTableWidget,QTableWidgetItem,QHeaderView,QFileDialog,QMessageBox,QDialog,QListWidget,QListWidgetItem,QGridLayout,QScrollArea,QTextEdit,QProgressBar,QCheckBox,QGroupBox)
import core,metadata,subtitle_match,subtitle_cache
CSS='''QWidget{background:#101827;color:#e8eef8;font:10pt "Segoe UI"}QPushButton{background:#263952;border:1px solid #39526d;border-radius:8px;padding:9px}QPushButton:hover{background:#345479}QPushButton#primary{background:#2879ed;color:white}QLineEdit,QComboBox,QSpinBox,QTableWidget,QTextEdit,QListWidget{background:#192638;border:1px solid #334862;border-radius:7px;padding:6px}QHeaderView::section{background:#253851;color:#fff;padding:8px;border:0}QGroupBox{border:1px solid #34465d;border-radius:10px;margin-top:10px;padding:12px}QGroupBox::title{subcontrol-origin:margin;left:12px;padding:0 5px}QProgressBar{border:0;background:#263952;text-align:center}QProgressBar::chunk{background:#2885ee}'''
class CopyWorker(QThread):
    update=Signal(int);done=Signal(list,list)
    def __init__(self,tasks):super().__init__();self.tasks=tasks
    def run(self):
        ok=[];errors=[]
        for i,(src,dst,name) in enumerate(self.tasks):
            try:ok.append(core.verified_copy(src,dst,name))
            except Exception as e:errors.append({'source':src,'error':str(e)})
            self.update.emit(int(100*(i+1)/len(self.tasks)))
        self.done.emit(ok,errors)
class SubtitleWorker(QThread):
    done=Signal(dict,str)
    status_update=Signal(str)
    def __init__(self,path,reference_folder=None,online=None):
        super().__init__()
        self.path=path
        self.reference_folder=reference_folder
        self.online=online
    def run(self):
        try:
            self.done.emit(subtitle_match.analyse_file(self.path,self.reference_folder,online=self.online,progress=self.status_update.emit),'')
        except Exception as exc:
            self.done.emit({},str(exc))

class SearchWorker(QThread):
    done=Signal(list,str)
    def __init__(self,key,query,kind):super().__init__();self.key=key;self.query=query;self.kind=kind
    def run(self):
        try:self.done.emit(metadata.TMDB(self.key).search(self.query,self.kind),'')
        except Exception as e:self.done.emit([],str(e))
class PosterWorker(QThread):
    """Fetch TMDB poster thumbnails off the UI thread; send image bytes only."""
    poster_ready=Signal(int,bytes)
    def __init__(self,poster_paths):
        super().__init__()
        self.poster_paths=list(poster_paths)
    def run(self):
        for i,path in enumerate(self.poster_paths):
            if self.isInterruptionRequested():return
            # Never accept arbitrary URLs from API data.
            if not isinstance(path,str) or not re.fullmatch(r"/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png)",path,re.I):
                continue
            try:
                req=urllib.request.Request('https://image.tmdb.org/t/p/w92'+path,
                        headers={'User-Agent':'MKVEpisodeManager/0.4.2'})
                with urllib.request.urlopen(req,timeout=4) as response:
                    data=response.read(600_001)
                if len(data)<=600_000 and not self.isInterruptionRequested():
                    self.poster_ready.emit(i,data)
            except (OSError,ValueError):
                pass

class SearchDialog(QDialog):
    def __init__(self,parent,key,kind,query):
        super().__init__(parent)
        self.setWindowTitle('Choose '+('movie' if kind=='movie' else 'TV series')+' from TMDB')
        self.resize(830,660)
        self.key=key;self.kind=kind;self.choice=None;self.worker=None;self.poster_worker=None
        layout=QVBoxLayout(self)
        heading=QLabel('Choose by poster, title and release year')
        heading.setStyleSheet('font-size:15pt;font-weight:700')
        layout.addWidget(heading)
        warning=QLabel('TMDB search suggestions only — these are not automatically verified '
                       'against your video. Check the DVD cover before approving the rename.')
        warning.setWordWrap(True)
        warning.setStyleSheet('color:#ffd58c;background:#303041;border:1px solid #846132;'
                              'padding:10px;border-radius:8px')
        layout.addWidget(warning)
        top=QHBoxLayout();self.query=QLineEdit(query)
        self.query.returnPressed.connect(self.search)
        top.addWidget(self.query)
        self.search_button=QPushButton('Search')
        self.search_button.clicked.connect(self.search)
        top.addWidget(self.search_button);layout.addLayout(top)
        self.status=QLabel('Searching TMDB…')
        layout.addWidget(self.status)
        self.results=QListWidget()
        self.results.setIconSize(QSize(74,110))
        self.results.setSpacing(4)
        self.results.setWordWrap(True)
        self.results.itemClicked.connect(lambda _:self.choose())
        self.results.itemDoubleClicked.connect(lambda _:self.choose())
        layout.addWidget(self.results)
        select=QPushButton('Use selected title')
        select.setObjectName('primary')
        select.clicked.connect(self.choose)
        layout.addWidget(select)
        self.search()
    def search(self):
        if not self.query.text().strip():return
        if self.worker and self.worker.isRunning():return
        self.stop_posters()
        self.results.clear()
        self.search_button.setEnabled(False)
        self.status.setText('Searching TMDB…')
        self.worker=SearchWorker(self.key,self.query.text().strip(),self.kind)
        self.worker.done.connect(self.show_results)
        self.worker.finished.connect(lambda:self.search_button.setEnabled(True))
        self.worker.start()
    def show_results(self,results,error):
        self.status.setText(error or f'{len(results)} possible titles — select by poster or name')
        poster_paths=[]
        for candidate in results:
            title=candidate.get('title') or candidate.get('name') or 'Untitled'
            date=candidate.get('release_date') or candidate.get('first_air_date') or ''
            overview=(candidate.get('overview') or 'No synopsis available')[:135]
            entry=QListWidgetItem(f'{title}  ({date[:4] or "Year unknown"})\n{overview}')
            entry.setData(Qt.UserRole,candidate)
            entry.setSizeHint(QSize(100,122))
            self.results.addItem(entry)
            poster_paths.append(candidate.get('poster_path'))
        if not results and not error:
            self.status.setText('No TMDB titles found. Try a different spelling.')
        if poster_paths:
            self.poster_worker=PosterWorker(poster_paths)
            self.poster_worker.poster_ready.connect(self.show_poster)
            self.poster_worker.start()
    def show_poster(self,index,data):
        if not (0<=index<self.results.count()):return
        image=QPixmap()
        if image.loadFromData(data):
            self.results.item(index).setIcon(QIcon(image))
    def stop_posters(self):
        if self.poster_worker and self.poster_worker.isRunning():
            self.poster_worker.requestInterruption()
            self.poster_worker.wait()
        self.poster_worker=None
    def choose(self):
        item=self.results.currentItem()
        if item is None:
            QMessageBox.information(self,'Choose a title','Click a movie or TV series first.')
            return
        self.choice=item.data(Qt.UserRole)
        self.accept()
    def done(self,result):
        self.stop_posters()
        if self.worker and self.worker.isRunning():
            self.worker.wait()
        super().done(result)
class Main(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('MKV Episode Manager • v0.4.2 Subtitle Identification Test');self.resize(1420,900)
        self.items=[];self.history=[];self.metadata={};self.episodes={};self.worker=None;self.search_worker=None;self.subtitle_worker=None;self.tmdb_key=os.environ.get('TMDB_API_KEY','')
        self.temp=tempfile.TemporaryDirectory(prefix='mkv_visual_')
        w=QWidget();self.setCentralWidget(w);v=QVBoxLayout(w);v.setContentsMargins(20,16,20,16)
        h=QLabel('MKV Episode Manager   /   Visual Identification');h.setStyleSheet('font-size:22pt;font-weight:700');v.addWidget(h)
        safety=QLabel('v0.4.2 TEST  •  TMDB + subtitle reference search + scene gallery  •  Manual episode review  •  Copy-only SHA-256 verified export');safety.setStyleSheet('color:#91bcff');v.addWidget(safety)
        r=QHBoxLayout();self.mode=QComboBox();self.mode.addItems(core.MODES);self.mode.currentTextChanged.connect(self.mode_changed)
        self.title=QLineEdit();self.title.setPlaceholderText('Series or movie title');self.title.textChanged.connect(self.title_changed)
        self.season=QSpinBox();self.season.setRange(0,99);self.season.setValue(1);self.season.valueChanged.connect(self.season_changed)
        self.key=QLineEdit(self.tmdb_key);self.key.setEchoMode(QLineEdit.Password);self.key.setPlaceholderText('TMDB API key or Read Access Token (not saved)')
        self.subdl_key=QLineEdit(os.environ.get('SUBDL_API_KEY',''));self.subdl_key.setEchoMode(QLineEdit.Password);self.subdl_key.setPlaceholderText('SubDL API key for automatic subtitle search (not saved)')
        for label,control,stretch in [('Mode',self.mode,1),('Title',self.title,3),('Season',self.season,1),('TMDB token',self.key,3)]:
            label_widget=QLabel(label)
            r.addWidget(label_widget);r.addWidget(control,stretch)
            if label=='Season':self.season_label=label_widget
        v.addLayout(r)
        sr=QHBoxLayout();sr.addWidget(QLabel('SubDL key'));sr.addWidget(self.subdl_key,1)
        sr.addWidget(QLabel('DVD title and season drive reference search; generic filenames are ignored.'))
        v.addLayout(sr)
        bar=QHBoxLayout()
        for name,callback in [('Import MKVs',self.import_folder),('Find movie / series',self.find_title),('Fetch season episodes',self.fetch_episodes),('Scene gallery',self.gallery),('Analyse subtitles',self.analyse_subtitles),('Import OCR SRT',self.import_ocr_srt),('Clear OCR cache',self.clear_ocr_cache),('Inspect selected',self.inspect_selected),('Save project',self.save_project),('Open project',self.open_project)]:
            b=QPushButton(name);b.clicked.connect(callback);bar.addWidget(b)
            if name=='Fetch season episodes':self.fetch_episodes_button=b
            if name=='Analyse subtitles':self.subtitle_button=b
        v.addLayout(bar)
        self.poster=QLabel('No poster selected');self.poster.setAlignment(Qt.AlignCenter);self.poster.setFixedSize(105,150);self.poster.setStyleSheet('background:#1c2a3e;border-radius:8px')
        summary=QHBoxLayout();summary.addWidget(self.poster)
        self.description=QLabel('Import a folder, then search TMDB. A metadata match does not prove the exact episode inside a file.');self.description.setWordWrap(True)
        summary.addWidget(self.description,1);v.addLayout(summary)
        self.table=QTableWidget(0,7);self.table.setHorizontalHeaderLabels(['Approve','Original MKV','Episode #','Episode / movie title','Year','Output filename','Inspection'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        for c,width in enumerate([80,240,90,245,70,360,250]):self.table.setColumnWidth(c,width)
        self.table.itemChanged.connect(self.changed);v.addWidget(self.table,1)
        self.log=QTextEdit();self.log.setReadOnly(True);self.log.setMaximumHeight(110);v.addWidget(self.log)
        bottom=QHBoxLayout();self.status=QLabel('Ready');bottom.addWidget(self.status,1)
        for name,callback in [('Diagnostics JSON',self.report),('Export approved copies',self.export)]:
            b=QPushButton(name);b.clicked.connect(callback)
            if name.startswith('Export'):b.setObjectName('primary');self.export_button=b
            bottom.addWidget(b)
        v.addLayout(bottom);self.progress=QProgressBar();self.progress.hide();v.addWidget(self.progress)
        self.mode_changed()
        self.note('Online TMDB search requires your own free TMDB API credentials. No key is saved in project files.')
    def note(self,msg):self.log.append(msg)
    def row(self):
        n=self.table.currentRow()
        if n<0 or n>=len(self.items):QMessageBox.information(self,'Select an MKV','Select a file row first.');return None
        return n
    def import_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Select MakeMKV folder')
        if not folder:return
        paths=sorted(p for p in Path(folder).rglob('*') if p.is_file() and p.suffix.lower()=='.mkv' and not p.is_symlink())
        if not paths:QMessageBox.warning(self,'No MKVs','No MKV files found');return
        self.items=[{'path':str(p.resolve()),'episode':'','title':'','year':'','proposed':'','approved':False,'technical':{}} for p in paths]
        # Preserve an explicitly entered DVD-cover title. Never guess identity
        # from MakeMKV output filenames such as C1_t00.mkv or title_t00.mkv.
        explicit_title=metadata.title_for_import(self.title.text(),paths[0].name)
        if not explicit_title:
            self.title.clear()
            self.note('Enter the movie or TV series title printed on your DVD cover. '
                      'Generic MakeMKV filenames are not used for identification.')
        self.refresh();self.note(f'Imported {len(paths)} MKVs (read-only; original filenames preserved).')
    def refresh(self):
        self.table.blockSignals(True);self.table.setRowCount(len(self.items))
        for row,x in enumerate(self.items):
            for col,value in enumerate([None,Path(x['path']).name,x.get('episode',''),x.get('title',''),x.get('year',''),x.get('proposed',''),self.tech_text(x)]):
                cell=QTableWidgetItem('' if value is None else str(value))
                if col==0:cell.setFlags(Qt.ItemIsUserCheckable|Qt.ItemIsEnabled|Qt.ItemIsSelectable);cell.setCheckState(Qt.Checked if x.get('approved') else Qt.Unchecked)
                if col in (1,6):cell.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable)
                self.table.setItem(row,col,cell)
        self.table.blockSignals(False);self.status.setText(f'{len(self.items)} MKVs • {sum(bool(x.get("approved")) for x in self.items)} approved')
    def tech_text(self,x):
        t=x.get('technical') or {}
        return f'{t.get("width","?")}×{t.get("height","?")} {t.get("codec","?")} {t.get("duration","?")}s' if t else 'Not inspected'
    def changed(self,cell):
        row=cell.row();col=cell.column()
        if row>=len(self.items):return
        x=self.items[row]
        if col==0:x['approved']=cell.checkState()==Qt.Checked
        elif col in (2,3,4):
            x[{2:'episode',3:'title',4:'year'}[col]]=cell.text();
            if col==2 and self.mode.currentText()!='Movie' and cell.text().strip() in self.episodes:x['title']=self.episodes[cell.text().strip()]
            x['proposed']=core.suggest(x,self.mode.currentText(),self.title.text(),self.season.value());x['approved']=False
        elif col==5:x['proposed']=cell.text();x['approved']=False
        self.refresh()
    def title_changed(self,*_):
        if not hasattr(self,'items'):return
        for x in self.items:x['proposed']=core.suggest(x,self.mode.currentText(),self.title.text(),self.season.value());x['approved']=False
        self.refresh()
    def season_changed(self,*_):self.title_changed()
    def mode_changed(self,*_):
        is_tv=self.mode.currentText()!='Movie'
        self.season_label.setVisible(is_tv)
        self.season.setVisible(is_tv)
        self.fetch_episodes_button.setVisible(is_tv)
        self.title_changed()
    def find_title(self):
        kind='movie' if self.mode.currentText()=='Movie' else 'tv'
        dialog=SearchDialog(self,self.key.text(),kind,self.title.text())
        if dialog.exec()!=QDialog.Accepted:return
        selected=dialog.choice;self.metadata={'kind':kind,'id':selected['id'],'poster_path':selected.get('poster_path'),'overview':selected.get('overview','')}
        title=selected.get('title') or selected.get('name') or '';date=selected.get('release_date') or selected.get('first_air_date') or ''
        self.title.setText(title);self.description.setText(f'{title} ({date[:4]})\n{selected.get("overview", "")}')
        if kind=='movie':
            for x in self.items:x['title']=title;x['year']=date[:4];x['proposed']=core.suggest(x,self.mode.currentText(),title,self.season.value());x['approved']=False
            self.refresh();self.note('Movie metadata populated from TMDB. Review the result and approve each output.')
        else:self.note('TV series selected. Click Fetch season episodes to retrieve the catalogue; assign actual episodes manually.')
        self.load_poster(selected.get('poster_path'))
    def load_poster(self,path):
        self.poster.setText('No poster')
        if not path:return
        try:
            request=urllib.request.Request('https://image.tmdb.org/t/p/w185'+path,headers={'User-Agent':'MKVEpisodeManager/0.4.1'})
            with urllib.request.urlopen(request,timeout=10) as response:data=response.read(2*1024*1024)
            pix=QPixmap();pix.loadFromData(data);self.poster.setPixmap(pix.scaled(105,150,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        except Exception:self.note('Poster download unavailable; metadata remains usable.')
    def fetch_episodes(self):
        if self.mode.currentText()=='Movie':QMessageBox.information(self,'TV only','Switch to a TV mode first.');return
        if self.metadata.get('kind')!='tv':QMessageBox.information(self,'Select series','Find and select a TMDB series first.');return
        try:episodes=metadata.TMDB(self.key.text()).season(self.metadata['id'],self.season.value())
        except Exception as e:QMessageBox.warning(self,'TMDB',str(e));return
        self.episodes={str(e['episode_number']):e.get('name','') for e in episodes}
        preview='\n'.join(f'E{int(n):02d}  {name}' for n,name in self.episodes.items())
        QMessageBox.information(self,'Season episode catalogue',f'{len(episodes)} episodes retrieved.\n\n{preview[:3500]}\n\nEnter an episode number in a row to fill its title. This is not content identification.')
        self.note(f'Retrieved {len(episodes)} TMDB episode entries for season {self.season.value()}.')
    def inspect_selected(self):
        row=self.row()
        if row is None:return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:self.items[row]['technical']=core.inspect(self.items[row]['path'])
        finally:QApplication.restoreOverrideCursor()
        self.refresh();self.note(f'Inspected {Path(self.items[row]["path"]).name}')
    def gallery(self):
        row=self.row()
        if row is None:return
        dialog=QDialog(self);dialog.setWindowTitle('Scene gallery — visual review, not automatic episode matching');dialog.resize(1000,680)
        v=QVBoxLayout(dialog);v.addWidget(QLabel('Six evenly spaced frames from the original MKV. No re-encoding or modification.'))
        grid=QGridLayout();v.addLayout(grid)
        folder=Path(self.temp.name)/f'gallery_{row}';folder.mkdir(exist_ok=True)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:images=core.frames(self.items[row]['path'],folder)
        except Exception as e:QMessageBox.warning(self,'Gallery unavailable',f'Install FFmpeg/FFprobe or check the file.\n{e}');dialog.close();return
        finally:QApplication.restoreOverrideCursor()
        for i,(file,seconds) in enumerate(images):
            box=QWidget();bv=QVBoxLayout(box);label=QLabel();label.setAlignment(Qt.AlignCenter)
            pix=QPixmap(file);label.setPixmap(pix.scaled(300,175,Qt.KeepAspectRatio,Qt.SmoothTransformation))
            bv.addWidget(label);bv.addWidget(QLabel(f'{seconds//60:02d}:{seconds%60:02d}'));grid.addWidget(box,i//3,i%3)
        dialog.exec()
    def analyse_subtitles(self):
        row=self.row()
        if row is None:return
        title=self.title.text().strip()
        api_key=self.subdl_key.text().strip()
        if not title or title.lower() in ('title','title_t00','mkv','mkv 00'):
            QMessageBox.information(self,'Enter DVD title',
                'Enter the actual movie or TV series name from the DVD cover before searching.')
            return
        online=None
        if api_key:
            online={'key':api_key,'title':title,
                    'kind':'movie' if self.mode.currentText()=='Movie' else 'tv',
                    'season':self.season.value() if self.mode.currentText()!='Movie' else None,
                    'tmdb_id':self.metadata.get('id') if self.metadata.get('kind')==(
                        'movie' if self.mode.currentText()=='Movie' else 'tv') else None}
        else:
            if QMessageBox.question(self,'SubDL key needed',
                'No SubDL API key is entered. Continue with subtitle track inspection only?\\n'
                'Online matching needs your own free SubDL API key.') != QMessageBox.Yes:
                return
        self.subtitle_row=row
        self.subtitle_button_busy(True)
        self.note('Analysing embedded subtitles; this may take a moment.')
        self.subtitle_worker=SubtitleWorker(self.items[row]['path'],online=online)
        self.subtitle_worker.done.connect(self.subtitle_done)
        self.subtitle_worker.status_update.connect(self.subtitle_progress)
        self.subtitle_worker.start()
    def subtitle_progress(self,message):
        self.note(message)
        self.status.setText('Subtitle analysis: ' + message)
    def import_ocr_srt(self):
        row=self.row()
        if row is None:return
        path,_=QFileDialog.getOpenFileName(self,'Select previously OCR-converted English subtitle file',
                                          '', 'SubRip subtitles (*.srt)')
        if not path:return
        try:
            tracks=subtitle_match.probe_subtitles(self.items[row]['path'])
            english=[t for t in tracks if t['needs_ocr'] and
                     t['language'].lower() in ('eng','en')]
            if not english:raise ValueError('No English image subtitle track found in this MKV.')
            chosen=next((t for t in english if not t.get('forced')),english[0])
            if not subtitle_match.read_reference(path):
                raise ValueError('This SRT contains no usable English dialogue.')
            if QMessageBox.question(self,'Confirm OCR import',
                    'This transcript must come from the selected MKV and its English subtitle track.\\n'
                    'Use it for future comparisons?')!=QMessageBox.Yes:return
            subtitle_cache.store(self.items[row]['path'],chosen['index'],path)
            self.note('Saved English OCR transcript locally. Future analysis will reuse it.')
            QMessageBox.information(self,'OCR cache','English transcript saved to local OCR cache.')
        except Exception as exc:
            QMessageBox.warning(self,'OCR import failed',str(exc))
    def clear_ocr_cache(self):
        if QMessageBox.question(self,'Clear cached OCR dialogue',
                'Delete all locally cached OCR subtitle text? Original MKVs will remain untouched.') != QMessageBox.Yes:return
        try:
            n=subtitle_cache.clear()
            QMessageBox.information(self,'OCR cache cleared',f'Deleted {n} cached subtitle files.')
        except OSError as exc:
            QMessageBox.warning(self,'Cache deletion failed',str(exc))
    def subtitle_button_busy(self,busy):
        if hasattr(self,'subtitle_button'):self.subtitle_button.setEnabled(not busy)
    def subtitle_done(self,report,error):
        self.subtitle_button_busy(False)
        self.status.setText('Ready')
        if error:
            QMessageBox.warning(self,'Subtitle analysis failed',error);self.note('Subtitle analysis failed.');return
        row=self.subtitle_row
        self.items[row]['subtitle_analysis']=report
        lines=[report['status'],'',f'Embedded subtitle streams: {len(report["tracks"])}']
        if 'online_reference_status' in report:
            lines.extend(['Online subtitle reference search:',report['online_reference_status'],''])
            for attempt in report.get('online_reference_attempts',[]):
                lines.append(' - '+attempt)
            if 'online_download_attempt_count' in report:
                lines.append('Reference downloads attempted: '+str(report['online_download_attempt_count']))
                for reason,count in sorted(report.get('online_download_diagnostics',{}).items()):
                    lines.append(' - '+str(count)+' × '+reason)
        if 'ocr_status' in report:
            lines.extend(['Image subtitle OCR:',report['ocr_status'],
                          'OCR dialogue cues: '+str(report.get('ocr_cue_count',0)),''])
        for track in report['tracks']:
            lines.append(f'Stream {track["index"]}: {track["language"]} / {track["codec"]} — {track["status"]} '
                         f'({track.get("cue_count",0)} dialogue cues)')
        if report['top_matches']:
            lines.extend(['','Reference subtitle matches (heuristic overlap, NOT probability of correctness):'])
            for match in report['top_matches'][:5]:
                lines.append(f'{match["name"]}: score {match["score"]}% | '
                             f'{match["matching_windows"]} matching 5-word windows | '
                             f'{match["matching_cues"]} matching cues | '
                             f'{"supported" if match["supported"] else "insufficient evidence"}')
        else:lines.extend(['','No supported content match. Movie/episode is unverified.'])
        lines.append('')
        lines.append('Candidate matches require your review. No filename has been approved automatically.')
        QMessageBox.information(self,'Subtitle analysis results','\n'.join(lines))
        self.note(f'Subtitle analysis: {Path(self.items[row]["path"]).name}: {report["status"]}')
    def save_project(self):
        path,_=QFileDialog.getSaveFileName(self,'Save project','','MKV project (*.json)')
        if not path:return
        try:core.save(path,{'mode':self.mode.currentText(),'title':self.title.text(),'season':self.season.value(),'metadata':self.metadata,'episodes':self.episodes,'items':self.items,'history':self.history});self.note('Project saved.')
        except Exception as e:QMessageBox.warning(self,'Save failed',str(e))
    def open_project(self):
        path,_=QFileDialog.getOpenFileName(self,'Open project','','MKV project (*.json)')
        if not path:return
        try:
            with open(path,encoding='utf8') as f:data=json.load(f)
            if data.get('mode') not in core.MODES:raise ValueError('Invalid project mode')
            for control in (self.mode,self.title,self.season):control.blockSignals(True)
            self.mode.setCurrentText(data['mode']);self.title.setText(data.get('title',''));self.season.setValue(int(data.get('season',1)))
            for control in (self.mode,self.title,self.season):control.blockSignals(False)
            self.items=data.get('items',[]);self.metadata=data.get('metadata',{});self.episodes=data.get('episodes',{});self.history=data.get('history',[])
            self.mode_changed()
            self.refresh();self.load_poster(self.metadata.get('poster_path'));self.note('Project restored. Check source paths and metadata before exporting.')
        except Exception as e:
            for control in (self.mode,self.title,self.season):control.blockSignals(False)
            QMessageBox.warning(self,'Open failed',str(e))
    def report(self):
        path,_=QFileDialog.getSaveFileName(self,'Save diagnostics','','JSON report (*.json)')
        if not path:return
        report={'version':'0.4.1','metadata':self.metadata,'title':self.title.text(),'mode':self.mode.currentText(),'files':[{'filename':Path(x['path']).name,'proposed':x.get('proposed'),'approved':x.get('approved'),'technical':x.get('technical')} for x in self.items],'export_history':self.history,'subtitle_analysis':[{'file':Path(x['path']).name,'result':x.get('subtitle_analysis')} for x in self.items], 'visual_identification':'Manual scene review only; no image-reference matching','audio_identification':'Not implemented'}
        try:core.save(path,report);self.note('Diagnostic report saved.')
        except Exception as e:QMessageBox.warning(self,'Report failed',str(e))
    def export(self):
        selected=[x for x in self.items if x.get('approved')]
        if not selected:QMessageBox.information(self,'Approval required','Tick Approve on reviewed rows first.');return
        names=[x.get('proposed','') for x in selected]
        if any(not n or n!=core.clean(n) or not n.lower().endswith('.mkv') for n in names):QMessageBox.warning(self,'Invalid names','Check approved output filenames.');return
        if len({n.lower() for n in names})!=len(names):QMessageBox.warning(self,'Duplicate names','Approved output filenames must be unique.');return
        folder=QFileDialog.getExistingDirectory(self,'Choose separate, empty output folder')
        if not folder:return
        try:
            core.validate_destination([x['path'] for x in self.items],folder)
            for name in names:
                if (Path(folder)/name).exists() or (Path(folder)/(name+'.part')).exists():raise FileExistsError('Output or .part already exists: '+name)
        except Exception as e:QMessageBox.warning(self,'Unsafe output',str(e));return
        if QMessageBox.question(self,'Confirm export',f'Copy {len(selected)} approved MKVs to:\n{folder}\n\nOriginals remain untouched. Verify each copy with SHA-256?')!=QMessageBox.Yes:return
        self.export_button.setEnabled(False);self.progress.show();self.progress.setValue(0)
        self.worker=CopyWorker([(x['path'],folder,x['proposed']) for x in selected]);self.worker.update.connect(self.progress.setValue);self.worker.done.connect(self.export_done);self.worker.start()
    def export_done(self,ok,errors):
        self.history.extend(ok);self.history.extend({'verified':False,**e} for e in errors)
        self.export_button.setEnabled(True);self.note(f'Export: {len(ok)} verified; {len(errors)} failed.')
        for e in errors:self.note('FAILED: '+e['error'])
        QMessageBox.information(self,'Export complete',f'{len(ok)} SHA-256 verified copies\n{len(errors)} failures\nOriginal MKVs untouched.')
if __name__=='__main__':
    app=QApplication(sys.argv);app.setStyle('Fusion');app.setStyleSheet(CSS);win=Main();win.show();sys.exit(app.exec())
