import sys
import subprocess
from PyQt6.QtWidgets import (QApplication, QWidget, QPushButton, QVBoxLayout, QFileDialog, QLabel,
                             QTextEdit, QProgressBar, QDialog, QLineEdit, QCheckBox, QMessageBox,
                             QListWidget, QListWidgetItem, QInputDialog, QHBoxLayout)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QIcon, QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import QListWidget, QAbstractItemView

import eyed3
import tempfile
import os

filelist = []

class ID3TagEditorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit ID3 Tags")
        self.layout = QVBoxLayout(self)
        self.artist_line_edit = QLineEdit(self)
        self.title_line_edit = QLineEdit(self)
        self.album_line_edit = QLineEdit(self)
        self.year_line_edit = QLineEdit(self)
        self.comment_text_edit = QTextEdit(self)
        self.layout.addWidget(QLabel("Artist:"))
        self.layout.addWidget(self.artist_line_edit)
        self.layout.addWidget(QLabel("Title:"))
        self.layout.addWidget(self.title_line_edit)
        self.layout.addWidget(QLabel("Album:"))
        self.layout.addWidget(self.album_line_edit)
        self.layout.addWidget(QLabel("Year:"))
        self.layout.addWidget(self.year_line_edit)
        self.layout.addWidget(QLabel("Comment:"))
        self.layout.addWidget(self.comment_text_edit)
        self.accept_button = QPushButton("OK", self)
        self.accept_button.clicked.connect(self.accept)
        self.layout.addWidget(self.accept_button)

    def set_tags(self, artist, title, album, year, comment):
        self.artist_line_edit.setText(artist)
        self.title_line_edit.setText(title)
        self.album_line_edit.setText(album)
        self.year_line_edit.setText(year)
        self.comment_text_edit.setText(comment)

    def get_tags(self):
        return (self.artist_line_edit.text(), self.title_line_edit.text(),
                self.album_line_edit.text(), self.year_line_edit.text(),
                self.comment_text_edit.toPlainText())

class FileListWidget(QListWidget):
    def __init__(self, *args, **kwargs):
        super(FileListWidget, self).__init__(*args, **kwargs)

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)


    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dropEvent(self, event: QDropEvent):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    self.addItem(url.toLocalFile())
            event.acceptProposedAction()
        else:
            super().dropEvent(event)

class CombineFilesThread(QThread):
    update_log = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished_successfully = pyqtSignal()

    def __init__(self, filelist, output_file, id3_tags, album_art_path):
        super().__init__()
        self.filelist = filelist
        self.output_file = output_file
        self.id3_tags = id3_tags
        self.album_art_path = album_art_path

    def run(self):
        if not self.filelist:
            self.update_log.emit("No files selected to combine.")
            return

        if os.path.exists(self.output_file):
            self.update_log.emit(f"Output file {self.output_file} already exists.")
            return

        strlist = "|".join(f"\"{file}\"" for file in self.filelist)  # Ensure paths are properly quoted
        print("running command")
        command = f"ffmpeg -y -i \"concat:{strlist}\" -acodec copy \"{self.output_file}\""
        print("now for real")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, bufsize=1, universal_newlines=True)
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                self.update_log.emit(output.strip())
                print(output.strip())

        rc = process.poll()
        if rc == 0:
            self.update_log.emit(f"Successfully combined files into {self.output_file}")
            self._update_id3_tags()
            self.finished_successfully.emit()
        else:
            self.update_log.emit(f"Error combining files with exit code {rc}")

    def _update_id3_tags(self):
        audiofile = eyed3.load(self.output_file)
        if audiofile.tag is None:
            audiofile.initTag()

        audiofile.tag.artist = self.id3_tags[0]
        audiofile.tag.title = self.id3_tags[1]
        audiofile.tag.album = self.id3_tags[2]
        audiofile.tag.recording_date = self.id3_tags[3]
        audiofile.tag.comments.set(self.id3_tags[4])

        if self.album_art_path:
            with open(self.album_art_path, 'rb') as album_art:
                audiofile.tag.images.set(3, album_art.read(), 'image/jpeg')
        
        audiofile.tag.save()

def open_file_dialog(log_viewer):
    global filelist

    file_dialog = QFileDialog()
    files, _ = file_dialog.getOpenFileNames(None, "Select Audio Files", "", "Audio Files (*.mp3 *.wav *.flac)")
    filelist = files
    if files:
        log_viewer.append("Selected files:\n" + "\n".join(files))
    else:
        log_viewer.append("No files selected.")

def create_window():
    app = QApplication(sys.argv)
    app.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)

    window = QWidget()
    window.setWindowTitle('Audiobook Maker')
    window.setWindowIcon(QIcon('your_icon_here.png'))  # Update your icon path

    layout = QVBoxLayout()

    file_list_widget = FileListWidget()
    layout.addWidget(file_list_widget)

    log_viewer = QTextEdit()
    log_viewer.setReadOnly(True)
    layout.addWidget(log_viewer)

    progress_bar = QProgressBar()
    layout.addWidget(progress_bar)

    def update_log(message):
        log_viewer.append(message)

    def on_combine_files():
        global thread  # Declare the thread as global or store it as an attribute of another object
        if not filelist:
            update_log("No files selected.")
            return

        editor = ID3TagEditorDialog(window)
        if filelist:
            # Initialize your ID3 editor dialog and populate it with data here
            if editor.exec() == QDialog.DialogCode.Accepted:
                id3_tags = editor.get_tags()
                album_art_path, _ = QFileDialog.getOpenFileName(window, "Select Album Art", "", "Images (*.png *.jpg *.jpeg)")
                output_file, _ = QFileDialog.getSaveFileName(window, "Save Output File", "", "MP3 files (*.mp3)")
                if output_file:
                    # Keep a reference to the thread
                    thread = CombineFilesThread(filelist, output_file, id3_tags, album_art_path)
                    thread.update_log.connect(update_log)
                    thread.finished.connect(thread.deleteLater)  # Ensure thread is properly disposed of after finishing
                    thread.finished_successfully.connect(lambda: QMessageBox.information(window, "Success", "Audio file successfully created!"))
                    thread.start()


    button_open = QPushButton('Select Files')
    button_open.clicked.connect(lambda: open_file_dialog(log_viewer,))
    layout.addWidget(button_open)

    button_combine = QPushButton('Combine Files and Edit ID3 Tags')
    button_combine.clicked.connect(on_combine_files)
    layout.addWidget(button_combine)

    window.setLayout(layout)
    window.resize(800, 600)  # Increased window size for better UI
    window.show()

    sys.exit(app.exec())

if __name__ == '__main__':
    create_window()
