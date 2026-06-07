import sys
from PySide6.QtWidgets import QApplication
from image_surfer.widgets.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Image Surfer")
    app.setOrganizationName("ImageSurfer")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()