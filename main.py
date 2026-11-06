import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QSpinBox, QSplitter,
    QTableWidget, QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget)

import core

STYLE = '''
QWidget {background:#111722;color:#e8eef7;font: 10pt 'Segoe UI';}
QGroupBox {border:1px solid #293448;border-radius:12px;margin-top:13px;padding:15px;font-weight:bold;}
QGroupBox::title {subcontrol-origin:margin;left:14px;padding:0 6px;}
QPushButton {background:#27374d;border:1px solid #3b506a;border-radius:8px;padding:9px 13px;font-weight:600;}
QPushButton:hover {background:#354e6d;}
QPushButton#primary {background:#2878e8;border-color:#2878e8;color:white;}
QPushButton#primary:hover {background:#388aff;}
QLineEdit,QSpinBox,QComboBox,QTextEdit,QTableWidget {background:#182232;border:1px solid #34445a;border-radius:7px;padding:5px;}
QHeaderView::section {background:#26354b;color:#dfe8f6;padding:8px;border:0;}
QTableWidget {gridline-color:#2b384d;selection-background-color:#28517f;}
QProgressBar {background:#243248;border:0;border-radius:5px;text-align:center;}
QProgressBar::chunk {background:#2e8bed;border-radius:5px;}
'''

class Worker(QThread):
    progress = Signal(int, str)
    finished_work = Signal(list, list)
    def __init__(self, tasks):
        super().__init__(); self.tasks = tasks
    def run(self):
        successes, errors = [], []
        for i, (src, folder, name) in enumerate(self.tasks):
            try: successes.append(core.verified_copy(src, folder, name))
            except Exception as e: errors.append({'source':src,'error':str(e)})
            self.progress.emit(int((i+1)/len(self.tasks)*100), f'{i+1}/{len(self.tasks)} processed')
        self.finished_work.emit(successes, errors)

class Main(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('MKV Episode Manager • v0.4 test build')
        self.resize(1360, 830)
        self.items = []; self.export_history = []; self.worker = None
        self.thumbnail_dir = tempfile.TemporaryDirectory(prefix='mkv_episode_thumbs_')
        root = QWidget(); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setSpacing(13); outer.setContentsMargins(22,18,22,18)
        title = QLabel('MKV Episode Manager   /   Import & Review'); title.setStyleSheet('font-size:22pt;font-weight:700;')
        outer.addWidget(title)
        hint = QLabel('SAFE TEST BUILD  •  Original MKVs are read-only  •  No overwriting  •  Manual identification and approval required')
        hint.setStyleSheet('color:#83b7fa;font-weight:600;'); outer.addWidget(hint)
        controls = QHBoxLayout()
        self.mode = QComboBox(); self.mode.addItems(core.MODES); self.mode.currentTextChanged.connect(self.refresh_names)
        self.series = QLineEdit(); self.series.setPlaceholderText('Series / movie name'); self.series.textChanged.connect(self.refresh_names)
        self.season = QSpinBox(); self.season.setRange(0,99); self.season.setValue(1); self.season.valueChanged.connect(self.refresh_names)
        for label, w in [('Import mode',self.mode),('Series / movie',self.series),('Season',self.season)]:
            controls.addWidget(QLabel(label)); controls.addWidget(w, 2 if w==self.series else 1)
        outer.addLayout(controls)
        buttons = QHBoxLayout()
        for text, callback in [('Import MKV folder',self.import_folder),('Open project',self.open_project),('Save project',self.save_project),('Inspect selected',self.inspect_selected),('Preview selected',self.preview_selected),('Thumbnail',self.make_thumbnail),('Check duplicates',self.check_duplicates)]:
            b = QPushButton(text); b.clicked.connect(callback); buttons.addWidget(b)
        outer.addLayout(buttons)
        splitter = QSplitter(Qt.Vertical)
        table_container = QWidget(); tl = QVBoxLayout(table_container); tl.setContentsMargins(0,0,0,0)
        self.table = QTableWidget(0,7)
        self.table.setHorizontalHeaderLabels(['Approve','Original file','Episode #','Episode / movie title','Year','Proposed filename','Technical details'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setColumnWidth(0,80); self.table.setColumnWidth(1,240); self.table.setColumnWidth(2,90)
        self.table.setColumnWidth(3,220); self.table.setColumnWidth(4,65)
        self.table.setColumnWidth(5,350); self.table.setColumnWidth(6,270)
        self.table.itemChanged.connect(self.table_changed)
        tl.addWidget(self.table)
        splitter.addWidget(table_container)
        lower = QWidget(); lower_layout = QHBoxLayout(lower); lower_layout.setContentsMargins(0,0,0,0)
        left = QGroupBox('Preview & evidence'); ll = QVBoxLayout(left)
        self.preview = QLabel('Select a file and click Thumbnail.\nFFmpeg is required for image generation.')
        self.preview.setMinimumSize(300,175); self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setStyleSheet('background:#1b283b;border-radius:9px;color:#9eb1c9;')
        ll.addWidget(self.preview)
        right = QGroupBox('Project diagnostics'); rl = QVBoxLayout(right)
        self.log = QTextEdit(); self.log.setReadOnly(True); rl.addWidget(self.log)
        lower_layout.addWidget(left,2); lower_layout.addWidget(right,3)
        splitter.addWidget(lower); splitter.setSizes([450,250]); outer.addWidget(splitter,1)
        bottom = QHBoxLayout()
        self.status = QLabel('Import a folder of MKVs to begin.'); bottom.addWidget(self.status,1)
        report = QPushButton('Export diagnostic report'); report.clicked.connect(self.export_report); bottom.addWidget(report)
        self.export_btn = QPushButton('Export approved copies'); self.export_btn.setObjectName('primary')
        self.export_btn.clicked.connect(self.export_copies); bottom.addWidget(self.export_btn)
        outer.addLayout(bottom)
        self.progress = QProgressBar(); self.progress.hide(); outer.addWidget(self.progress)
        self.log_message('v0.4 test build started. Automatic dialogue-based episode identification is NOT implemented.')
    def log_message(self, msg): self.log.append(msg)
    def current_row(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.items):
            QMessageBox.information(self,'Select a file','Please select a file row first.'); return None
        return row
    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self,'Select folder containing MakeMKV files')
        if not folder: return
        paths = sorted(p for p in Path(folder).rglob('*') if p.is_file() and p.suffix.lower()=='.mkv' and not p.is_symlink())
        if not paths:
            QMessageBox.warning(self,'No MKVs','No MKV files were found.'); return
        self.items = [{'path':str(p.resolve()),'episode':'','title':'','year':'','approved':False,'proposed':'','technical':{}} for p in paths]
        self.populate(); self.log_message(f'Imported {len(paths)} MKVs from {folder} (read-only).')
    def populate(self):
        self.table.blockSignals(True); self.table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            check = QTableWidgetItem(); check.setFlags(Qt.ItemIsEnabled|Qt.ItemIsUserCheckable|Qt.ItemIsSelectable)
            check.setCheckState(Qt.Checked if item.get('approved') else Qt.Unchecked)
            self.table.setItem(row,0,check)
            orig = QTableWidgetItem(Path(item['path']).name); orig.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable)
            orig.setToolTip(item['path']); self.table.setItem(row,1,orig)
            for col, key in [(2,'episode'),(3,'title'),(4,'year'),(5,'proposed')]:
                self.table.setItem(row,col,QTableWidgetItem(str(item.get(key,'') or '')))
            tech = item.get('technical') or {}
            summary = f"{tech.get('width') or '?'}×{tech.get('height') or '?'} | {tech.get('video_codec') or '?'} | {tech.get('duration_seconds') or '?'}s | {tech.get('size_bytes',0)//(1024*1024)} MiB" if tech else 'Not inspected'
            detail = QTableWidgetItem(summary); detail.setFlags(Qt.ItemIsEnabled|Qt.ItemIsSelectable)
            self.table.setItem(row,6,detail)
        self.table.blockSignals(False)
        self.status.setText(f'{len(self.items)} imported • {sum(x.get("approved",False) for x in self.items)} approved')
    def table_changed(self, cell):
        row = cell.row(); col = cell.column()
        if row>=len(self.items): return
        item = self.items[row]
        if col==0: item['approved'] = cell.checkState()==Qt.Checked
        elif col in (2,3,4):
            item[{2:'episode',3:'title',4:'year'}[col]]=cell.text()
            item['approved']=False
            item['proposed']=core.suggested_name(item,self.mode.currentText(),self.series.text(),self.season.value())
        elif col==5:
            item['proposed']=cell.text(); item['approved']=False
        self.populate()
    def refresh_names(self, *_):
        if not hasattr(self,'items'): return
        for item in self.items:
            item['proposed']=core.suggested_name(item,self.mode.currentText(),self.series.text(),self.season.value())
            item['approved']=False
        self.populate()
    def inspect_selected(self):
        row=self.current_row()
        if row is None:return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try: self.items[row]['technical']=core.inspect(self.items[row]['path'])
        finally: QApplication.restoreOverrideCursor()
        self.populate(); self.log_message(f'Inspected {Path(self.items[row]["path"]).name}: {self.items[row]["technical"]}')
    def preview_selected(self):
        row=self.current_row()
        if row is None:return
        try: os.startfile(self.items[row]['path']) if sys.platform=='win32' else subprocess.Popen(['xdg-open',self.items[row]['path']])
        except Exception as e: QMessageBox.warning(self,'Preview failed',str(e))
    def make_thumbnail(self):
        row=self.current_row()
        if row is None:return
        out=Path(self.thumbnail_dir.name)/f'thumb_{row}.jpg'
        try:
            core.thumbnail(self.items[row]['path'],out)
            pix=QPixmap(str(out)); self.preview.setPixmap(pix.scaled(520,280,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        except Exception as e: QMessageBox.warning(self,'Thumbnail unavailable',f'Install FFmpeg or check the MKV.\n{e}')
    def check_duplicates(self):
        if not self.items:return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try: pairs=core.duplicates(self.items)
        except Exception as e: QMessageBox.warning(self,'Duplicate check failed',str(e)); return
        finally: QApplication.restoreOverrideCursor()
        if pairs:
            for a,b in pairs: self.log_message(f'Identical SHA-256: rows {a+1} and {b+1}')
        else: self.log_message('No byte-identical duplicate MKVs detected.')
        self.log_message(f'Manual numbering gaps: {core.missing_episodes(self.items,self.mode.currentText())} (not verified against official season list)')
    def project_data(self):
        return {'mode':self.mode.currentText(),'series':self.series.text(),'season':self.season.value(),
                'items':self.items,'export_history':self.export_history}
    def save_project(self):
        p,_=QFileDialog.getSaveFileName(self,'Save project','','MKV project (*.json)')
        if p:
            try: core.save_project(p,self.project_data()); self.log_message(f'Project saved: {p}')
            except Exception as e: QMessageBox.warning(self,'Save failed',str(e))
    def open_project(self):
        p,_=QFileDialog.getOpenFileName(self,'Open project','','MKV project (*.json)')
        if not p:return
        try:
            data=core.load_project(p)
            self.mode.blockSignals(True); self.series.blockSignals(True); self.season.blockSignals(True)
            self.mode.setCurrentText(data['mode']); self.series.setText(data.get('series',''))
            self.season.setValue(int(data.get('season',1)))
            self.mode.blockSignals(False); self.series.blockSignals(False); self.season.blockSignals(False)
            self.items=data.get('items',[]); self.export_history=data.get('export_history',[])
            self.populate()
            missing=[x['path'] for x in self.items if not Path(x['path']).is_file()]
            self.log_message(f'Loaded project: {p}. Missing source files: {len(missing)}')
        except Exception as e: QMessageBox.warning(self,'Open failed',str(e))
    def export_report(self):
        p,_=QFileDialog.getSaveFileName(self,'Export diagnostics','','JSON report (*.json)')
        if not p:return
        report={'app_version':core.APP_VERSION,'mode':self.mode.currentText(),'series':self.series.text(),
                'items':[{'file_name':Path(x['path']).name,'episode':x.get('episode'),
                          'title':x.get('title'),'proposed':x.get('proposed'),
                          'approved':x.get('approved'),'technical':x.get('technical')} for x in self.items],
                'manual_episode_gaps':core.missing_episodes(self.items,self.mode.currentText()),
                'export_history':self.export_history,
                'database_status':'Online metadata providers not integrated in this build',
                'identification_status':'Manual assignment only; automatic matching not integrated'}
        try:
            with open(p,'w',encoding='utf-8') as f: json.dump(report,f,indent=2)
            self.log_message(f'Diagnostic report written: {p}')
        except Exception as e: QMessageBox.warning(self,'Report failed',str(e))
    def export_copies(self):
        approved=[x for x in self.items if x.get('approved')]
        if not approved:
            QMessageBox.information(self,'Nothing approved','Approve at least one verified filename.'); return
        names=[x.get('proposed','') for x in approved]
        if any(not n or n!=core.clean_name(n) or not n.lower().endswith('.mkv') for n in names):
            QMessageBox.warning(self,'Invalid filename','Fix the approved filenames before exporting.');return
        if len({n.lower() for n in names})!=len(names):
            QMessageBox.warning(self,'Duplicate output names','Two approved rows have the same filename.');return
        folder=QFileDialog.getExistingDirectory(self,'Select a separate destination folder (not the source)')
        if not folder:return
        try:
            core.ensure_safe_destination([x['path'] for x in self.items],folder)
            existing=[n for n in names if (Path(folder)/n).exists() or (Path(folder)/(n+'.part')).exists()]
            if existing:raise FileExistsError('Existing output/partial file: '+', '.join(existing[:4]))
        except Exception as e: QMessageBox.warning(self,'Unsafe destination',str(e));return
        reply=QMessageBox.question(self,'Confirm verified copy',f'Copy {len(approved)} approved MKV(s) to:\n{folder}\n\nEach copy will be SHA-256 verified. Originals remain untouched. Continue?')
        if reply!=QMessageBox.Yes:return
        tasks=[(x['path'],folder,x['proposed']) for x in approved]
        self.export_btn.setEnabled(False); self.progress.setValue(0); self.progress.show()
        self.worker=Worker(tasks)
        self.worker.progress.connect(lambda v,msg:(self.progress.setValue(v),self.status.setText(msg)))
        self.worker.finished_work.connect(self.export_finished)
        self.worker.start()
    def export_finished(self,successes,errors):
        self.export_history.extend(successes)
        self.export_history.extend({'verified':False,**x} for x in errors)
        self.export_btn.setEnabled(True)
        self.log_message(f'Export completed: {len(successes)} verified; {len(errors)} errors.')
        for e in errors:self.log_message(f'FAILED: {e["source"]}: {e["error"]}')
        QMessageBox.information(self,'Copy results',f'{len(successes)} verified copies.\n{len(errors)} failures.\nOriginal MKVs were not modified.\nSave the project or export a report to retain these results.')

if __name__=='__main__':
    app=QApplication(sys.argv); app.setStyle('Fusion'); app.setStyleSheet(STYLE)
    window=Main(); window.show(); sys.exit(app.exec())