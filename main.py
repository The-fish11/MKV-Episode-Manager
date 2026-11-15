import json,os,sys,tempfile,urllib.request
from pathlib import Path
from PySide6.QtCore import Qt,QThread,Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,QPushButton,QComboBox,QSpinBox,QTableWidget,QTableWidgetItem,QHeaderView,QFileDialog,QMessageBox,QDialog,QListWidget,QListWidgetItem,QGridLayout,QScrollArea,QTextEdit,QProgressBar,QCheckBox,QGroupBox)
import core,metadata
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
class SearchWorker(QThread):
    done=Signal(list,str)
    def __init__(self,key,query,kind):super().__init__();self.key=key;self.query=query;self.kind=kind
    def run(self):
        try:self.done.emit(metadata.TMDB(self.key).search(self.query,self.kind),'')
        except Exception as e:self.done.emit([],str(e))
class SearchDialog(QDialog):
    def __init__(self,parent,key,kind,query):
        super().__init__(parent);self.setWindowTitle('Find '+('movie' if kind=='movie' else 'TV series')+' on TMDB');self.resize(650,510)
        self.key=key;self.kind=kind;self.choice=None;self.worker=None
        layout=QVBoxLayout(self);top=QHBoxLayout();self.query=QLineEdit(query);top.addWidget(self.query)
        b=QPushButton('Search');b.clicked.connect(self.search);top.addWidget(b);layout.addLayout(top)
        self.status=QLabel('Search by title; select the correct year and description.');layout.addWidget(self.status)
        self.results=QListWidget();self.results.itemDoubleClicked.connect(lambda _:self.choose());layout.addWidget(self.results)
        select=QPushButton('Use selected title');select.setObjectName('primary');select.clicked.connect(self.choose);layout.addWidget(select)
        self.search()
    def search(self):
        if not self.query.text().strip():return
        self.results.clear();self.status.setText('Searching TMDB…')
        self.worker=SearchWorker(self.key,self.query.text().strip(),self.kind)
        self.worker.done.connect(self.show_results);self.worker.start()
    def show_results(self,results,error):
        self.status.setText(error or f'{len(results)} matches — double-click a result to select')
        for item in results:
            title=item.get('title') or item.get('name') or 'Untitled';date=item.get('release_date') or item.get('first_air_date') or ''
            summary=(item.get('overview') or '')[:170]
            entry=QListWidgetItem(f'{title} ({date[:4] or "year unknown"})\n{summary}')
            entry.setData(Qt.UserRole,item);self.results.addItem(entry)
    def choose(self):
        row=self.results.currentItem()
        if row is None:return
        self.choice=row.data(Qt.UserRole);self.accept()
class Main(QMainWindow):
    def __init__(self):
        super().__init__();self.setWindowTitle('MKV Episode Manager • v0.4.1 Visual Identification');self.resize(1420,900)
        self.items=[];self.history=[];self.metadata={};self.episodes={};self.worker=None;self.search_worker=None;self.tmdb_key=os.environ.get('TMDB_API_KEY','')
        self.temp=tempfile.TemporaryDirectory(prefix='mkv_visual_')
        w=QWidget();self.setCentralWidget(w);v=QVBoxLayout(w);v.setContentsMargins(20,16,20,16)
        h=QLabel('MKV Episode Manager   /   Visual Identification');h.setStyleSheet('font-size:22pt;font-weight:700');v.addWidget(h)
        safety=QLabel('v0.4.1  •  Metadata search + scene gallery  •  Manual episode review  •  Copy-only SHA-256 verified export');safety.setStyleSheet('color:#91bcff');v.addWidget(safety)
        r=QHBoxLayout();self.mode=QComboBox();self.mode.addItems(core.MODES);self.mode.currentTextChanged.connect(self.mode_changed)
        self.title=QLineEdit();self.title.setPlaceholderText('Series or movie title');self.title.textChanged.connect(self.title_changed)
        self.season=QSpinBox();self.season.setRange(0,99);self.season.setValue(1);self.season.valueChanged.connect(self.season_changed)
        self.key=QLineEdit(self.tmdb_key);self.key.setEchoMode(QLineEdit.Password);self.key.setPlaceholderText('TMDB API key or Read Access Token (not saved)')
        for label,control,stretch in [('Mode',self.mode,1),('Title',self.title,3),('Season',self.season,1),('TMDB token',self.key,3)]:
            label_widget=QLabel(label)
            r.addWidget(label_widget);r.addWidget(control,stretch)
            if label=='Season':self.season_label=label_widget
        v.addLayout(r)
        bar=QHBoxLayout()
        for name,callback in [('Import MKVs',self.import_folder),('Find movie / series',self.find_title),('Fetch season episodes',self.fetch_episodes),('Scene gallery',self.gallery),('Inspect selected',self.inspect_selected),('Save project',self.save_project),('Open project',self.open_project)]:
            b=QPushButton(name);b.clicked.connect(callback);bar.addWidget(b)
            if name=='Fetch season episodes':self.fetch_episodes_button=b
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
        if not self.title.text().strip():self.title.setText(metadata.guess_title(paths[0].name))
        self.refresh();self.note(f'Imported {len(paths)} MKVs (read-only).')
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
        report={'version':'0.4.1','metadata':self.metadata,'title':self.title.text(),'mode':self.mode.currentText(),'files':[{'filename':Path(x['path']).name,'proposed':x.get('proposed'),'approved':x.get('approved'),'technical':x.get('technical')} for x in self.items],'export_history':self.history,'visual_identification':'Manual scene review only; no image-reference matching','audio_identification':'Not implemented'}
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
