#! /usr/bin/env python3
# -*- coding: utf-8 -*-

# O3METER
# Copyright (C) 2018 Orlando Garcia-Feal - Universidade de Vigo - orlando@uvigo.es

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import sys, os, shutil, time
import numpy

from PyQt5.QtWidgets import *
from PyQt5.QtGui import * 
from PyQt5.QtCore import *


################################################################################
#
# This class defines methods to make HUE <=> OZONE SCALE conversion.
#
# Hue values in a HSV representation can vary from 0 to 359. In our Ozone Scale
# the hue of the samples can move from the yellow (no ozone at all) to blue
# (max amount of ozone measurable). Hence our scale overlaps the HSV hue
# values, so we should map HSV hue values to our Ozone Scale value. This is
# values from 60 to 0 followed by values from 359 to 240 will be mapped to
# range values [0, 180].
#
# Hue: 0-359
# Scale: [60..0] & [359..240] ==> [0..180]
#
class HueScale():
    ## Given a HSV hue value will return an Ozone Scale value.
    def hueToScale(hue):
        if hue <= 60 :
            return abs(hue - 60)
        return abs(hue - 359) + 61

    ## The inverse function is itself
    def scaleToHue(scale):
        return HueScale.hueToScale(scale)

################################################################################
#
# This widget will show a pointer over a Ozone color scale. This scale vary from
# yellow to blue.
#
class ScaleWidget(QWidget):
    hue = 0
    
    def __init__(self, parent):
        super().__init__(parent)

    ## QT Slot. Updates the widget color value.
    def updatePointer(self, color):
        self.color = color
        self.update()

    ## Draws the widget's contents when a QPaintEvent occurs.
    def paintEvent(self, paintEvent):
        painter = QPainter(self)
        gradient = QLinearGradient(0, 0, self.width(), 0);

        # Standard 0-360 hue scale
        # for i in range(0, 7):
        #     gradient.setColorAt(i * (1 / 6), QColor.fromHsv(60 * i if i < 6 else 359, 255, 255));

        # Defines the gradient of the Ozone scale
        gradient.setColorAt(0, QColor.fromHsv(60, 255, 255));
        gradient.setColorAt(1/3, QColor.fromHsv(0, 255, 255));
        gradient.setColorAt(2/3., QColor.fromHsv(300, 255, 255));
        gradient.setColorAt(1, QColor.fromHsv(240, 255, 255));
        
        painter.fillRect(0, 0, self.width(), self.height(), gradient);

        colordisp = (self.width() * self.color) / 180
        points = QPolygonF([QPointF(-10.0 + colordisp, 0.0),
                            QPointF(0.0 + colordisp, 10.0),
                            QPointF(10.0 + colordisp, 0.0)])

        painter.setBrush(Qt.SolidPattern)
        painter.drawPolygon(points)

################################################################################
#        
# This thread computes the mean of all the pixels for a given region in the
# image. From this mean, a value of the Ozone Scale is obtained.
#
# This calculation can be time consuming on some slow computers. Therefore, this
# calculation is launched in a non-blocking thread.
#
class CalculationThread(QThread):
    calculationFinished = pyqtSignal(int)

    ## If the constructor is initialized with just the image array the whole
    # image will be processed.
    # @param arr numpy array with the image data
    # @param imgSize size of the image
    # @param imgSize size of the label in the interface
    # @param origin point of origin of the selection rectangle
    # @param destination point of destination of the selection rectangle 
    def __init__(self, arr, imgSize=0, lsize=0, origin=0, destination=0):
        self.imgSize = imgSize
        self.arr = arr
        self.lsize = lsize
        self.origin = origin
        self.destination = destination
        super().__init__()

    ## Computes the hue for the darker pixels of the whole image
    def computeAll(self):
        redPixels = self.arr[:, :, 2].reshape(-1)
        greenPixels = self.arr[:, :, 1].reshape(-1)
        bluePixels = self.arr[:, :, 0].reshape(-1)

        nps = redPixels.size

        values_t = numpy.fmax(redPixels, greenPixels)
        values = numpy.fmax(values_t, bluePixels)

        rvals = numpy.where(values < 150, redPixels, numpy.zeros(nps))
        gvals = numpy.where(values < 150, greenPixels, numpy.zeros(nps))
        bvals = numpy.where(values < 150, bluePixels, numpy.zeros(nps))

        nvals = numpy.count_nonzero(rvals)

        # Workaround for too bright pictures
        if nvals < 100 :
            rvals = numpy.where(values < 250, redPixels, numpy.zeros(nps))
            gvals = numpy.where(values < 250, greenPixels, numpy.zeros(nps))
            bvals = numpy.where(values < 250, bluePixels, numpy.zeros(nps))
            nvals = numpy.count_nonzero(rvals)

        print(nvals)

        rMean = int(numpy.asscalar(numpy.sum(rvals) / nvals))
        gMean = int(numpy.asscalar(numpy.sum(gvals) / nvals))
        bMean = int(numpy.asscalar(numpy.sum(bvals) / nvals))

        value = HueScale.hueToScale(QColor(rMean, gMean, bMean).hue())
        
        print("Hue of the stripe: " + str(value))
        self.calculationFinished.emit(value)

    def computeRegion(self):
        # Computes the corresponding coordinates of the selection in the
        # original image
        xo = int((min(self.origin.x(), self.destination.x()) * self.imgSize.width()) / self.lsize.width())
        xd = int((max(self.origin.x(), self.destination.x()) * self.imgSize.width()) / self.lsize.width()) + 1
        yo = int((min(self.origin.y(), self.destination.y()) * self.imgSize.height()) / self.lsize.height())
        yd = int((max(self.origin.y(), self.destination.y()) * self.imgSize.height()) / self.lsize.height()) + 1

        # Extracts a submatrix for each color
        redPixels = self.arr[yo:yd, xo:xd, 2]
        greenPixels = self.arr[yo:yd, xo:xd, 1]
        bluePixels = self.arr[yo:yd, xo:xd, 0]

        # Computes the mean value for each color
        rMean = int(numpy.asscalar(redPixels.mean()))
        gMean = int(numpy.asscalar(greenPixels.mean()))
        bMean = int(numpy.asscalar(bluePixels.mean()))

        value = HueScale.hueToScale(QColor(rMean, gMean, bMean).hue())
        print("Hue of the region: " + str(value))            
        self.calculationFinished.emit(value)
        
    ## Launch the calculation
    def run(self):
        if self.imgSize == 0:
            self.computeAll()
        else:
            self.computeRegion()

################################################################################
#
# This widget implements a custom image viewer
#
class SelectableImage(QLabel):
    rubberBand = 0
    scaleFactor = 1.0
    hueCalculated = pyqtSignal(int)
    
    def __init__(self, widget):
        super().__init__(widget)

    ## Scales the image by the given factor
    # @param factor Zoom factor
    # @returns Current zoom factor
    def scale(self, factor):
        self.scaleFactor = self.scaleFactor * factor
        self.resize(self.scaleFactor * self.pixmap().size())
        return self.scaleFactor

    ## When the mouse is pressed down over the image, a QRubberBand is created
    # and the coordinates are saved.
    def mousePressEvent(self, event):
        self.origin = event.pos()        
        if not self.rubberBand:
            self.rubberBand = QRubberBand(QRubberBand.Rectangle, self)
        self.rubberBand.setGeometry(QRect(self.origin, QSize()))
        self.rubberBand.show()

    ## When the mouse is moved with a button pressed, the rectangle geometry is
    # updated.
    def mouseMoveEvent(self, event):
        self.rubberBand.setGeometry(QRect(self.origin, event.pos()).normalized())

    ## When the mouse button is released, a new CalculationThread is created
    # with te data of the selection. A progress dialog is launched while the
    # computation is performed.
    def mouseReleaseEvent(self, event):
        progress = QProgressDialog(self)
        progress.setLabelText("Computing...")
        progress.setCancelButton(None)
        progress.setMaximum(0)
        progress.setMinimum(0)

        wthread = CalculationThread(self.arr, self.pixmap().size(), self.size(), self.origin, event.pos())
        wthread.calculationFinished.connect(progress.cancel)
        wthread.calculationFinished.connect(self.hueCalculated)
                
        wthread.start()
        progress.exec()

    ## Load a RAW file given a file name. 
    def loadRaw(self, fileName):
        dcpath = shutil.which("dcraw")
        if dcpath == None :
            # Dcraw is not installed on the system
            self.statusBar().showMessage("Cannot open: "+fileName)
            QMessageBox.information(self, QGuiApplication.applicationDisplayName(),
                                    "Cannot open file: dcraw is not present in the system.")            
            return False

        # Dcraw is present in the system :D        
        progress = QProgressDialog()
        progress.setLabelText("Processing RAW data...")
        progress.setCancelButton(None)
        progress.setMaximum(0)
        progress.setMinimum(0)

        dcraw = QProcess()
        dcraw.finished.connect(progress.cancel)
        dcraw.start(dcpath, ["-c", "-w", "-b", "2.0", fileName])
                
        progress.exec()        
        self.setImage(QImage.fromData(dcraw.readAllStandardOutput()))

        return True

    ## Load an image (non RAW) given a file name.
    def loadImage(self, fileName):
        reader = QImageReader(fileName)
        reader.setAutoTransform(True)
        newImage = reader.read()
        
        if (newImage.isNull()) :
            self.statusBar().showMessage("Cannot open: "+fileName)
            QMessageBox.information(self, QGuiApplication.applicationDisplayName(),
                                    "Cannot open file: "+reader.errorString())
            return False        
        
        self.setImage(newImage)
        return True

    ## Sets an image in the widget. The image is also converted into an numpy
    # array to be processed later.
    def setImage(self, newImage):
        ptr = newImage.convertToFormat(4).constBits()
        ptr.setsize(newImage.byteCount())
        self.arr = numpy.array(ptr).reshape(newImage.height(), newImage.width(), 4)  #  Copies the data
        
        self.setPixmap(QPixmap.fromImage(newImage))
        self.scaleFactor = 1.0
        self.adjustSize()

        progress = QProgressDialog(self)
        progress.setLabelText("Computing...")
        progress.setCancelButton(None)
        progress.setMaximum(0)
        progress.setMinimum(0)

        wthread = CalculationThread(self.arr)
        wthread.calculationFinished.connect(progress.cancel)
        wthread.calculationFinished.connect(self.hueCalculated)
                
        wthread.start()
        progress.exec()

        if (self.rubberBand):
            self.rubberBand.hide()

################################################################################
#
# Main window class
#
class MainWindow(QMainWindow):
    
    def __init__(self):
        super().__init__()
        self.initUI()

    ## Shows a dialog to open a new file
    def openf(self):
        dialog = QFileDialog(self, "Open File")
        if not dialog.exec() :
            return
        if (len(dialog.selectedFiles()) > 0):
            fileName = dialog.selectedFiles()[0]

            self.currentFile = fileName

            self.setWindowFilePath(fileName)
            self.setWindowTitle('O3METER - ' + fileName)

            self.updateColor(0)
            self.lcd.display(0)
            
            if fileName.lower().endswith('.cr2'):
                if not self.simage.loadRaw(fileName):
                    return
            else:
                if not self.simage.loadImage(fileName):
                    return

            self.scrollArea.setVisible(True)
            self.gridc.setVisible(True)
            
            self.zoominAction.setEnabled(True)
            self.zoomoutAction.setEnabled(True)
            self.fittowindowAction.setEnabled(True)

            self.scale.updatePointer(0)

            self.fittowindow()

            self.statusBar().showMessage("Opened: " + fileName)

    ## Save the hue calculation to a log file
    def logValue(self, value):
        f = open('ozone.log','a')
        f.write(self.currentFile + " " + str(value) + "\n")
        f.close()

    ## Qt Slot: zooms in the image.
    def zoomin(self):
        self.scaleImage(1.25)

    ## Qt Slot: zooms out the image.
    def zoomout(self):
        self.scaleImage(0.8)

    ## Qt Slot: fits the image to the window.
    def fittowindow(self):
        wsize = self.scrollArea.viewport().size()
        if wsize.width() == 0 :
            wsize.setWidth(self.splitter.width() - self.gridc.maximumWidth())            
        
        isize = self.simage.pixmap().size()
        
        wfactor = wsize.width() / isize.width()
        hfactor = wsize.height() / isize.height()

        self.simage.scaleFactor = 1.0
        self.scaleImage(min(wfactor, hfactor))

    ## Adjusts a scroll bar by a given factor.
    def adjustScrollBar(self, scrollBar, factor):
        scrollBar.setValue(factor * scrollBar.value() + ((factor - 1) * scrollBar.pageStep()/2))

    ## Qt Slot: scales the image by a given factor.
    def scaleImage(self, factor):
        scaleFactor = self.simage.scale(factor)
        self.adjustScrollBar(self.scrollArea.horizontalScrollBar(), factor)
        self.adjustScrollBar(self.scrollArea.verticalScrollBar(), factor)
        self.statusBar().showMessage("Scaled to : " + str(int(scaleFactor * 100))+"%")

    ## Qt Slot: changes the hue of the color widget.
    def updateColor(self, hue):
        self.palette.setColor(QPalette.Background, QColor.fromHsv(HueScale.scaleToHue(hue), 255, 255))
        self.colorw.setPalette(self.palette)

    ## Qt Slot: shows the about dialog.
    def about(self):
        QMessageBox.about(self, "About O3METER",
            "Copyright (C) 2018 - Universidade de Vigo <br/> \
             Orlando Garcia-Feal - <a href=mailto:orlando@uvigo.es>orlando@uvigo.es</a>  <br/><br/> \
            This program is free software; you can redistribute it and/or \
            modify it under the terms of the GNU General Public License \
            as published by the Free Software Foundation; either version 3 \
            of the License, or (at your option) any later version. \
            <br/><br/> \
            This program is distributed in the hope that it will be useful, \
            but WITHOUT ANY WARRANTY; without even the implied warranty of \
            MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the \
            GNU General Public License for more details. \
            <br/><br/> \
            You should have received a copy of the GNU General Public License \
            along with this program.  If not, see <https://www.gnu.org/licenses/>.")

    ## Initializes the user interface
    def initUI(self):               

        # Define actions        
        self.openAction = QAction(QIcon.fromTheme('document-open'), '&Open', self)
        self.openAction.setShortcut('Ctrl+O')
        self.openAction.setStatusTip('Open RAW file')
        self.openAction.triggered.connect(self.openf)
        
        self.exitAction = QAction(QIcon.fromTheme('application-exit'), '&Exit', self)        
        self.exitAction.setShortcut('Ctrl+Q')
        self.exitAction.setStatusTip('Exit application')
        self.exitAction.triggered.connect(qApp.quit)

        self.zoominAction = QAction(QIcon.fromTheme('zoom-in'), 'Zoom in', self)
        self.zoominAction.setShortcut('Ctrl++')
        self.zoominAction.setStatusTip("Zoom In")
        self.zoominAction.setEnabled(False)
        self.zoominAction.triggered.connect(self.zoomin)

        self.zoomoutAction = QAction(QIcon.fromTheme('zoom-out'), 'Zoom out', self)
        self.zoomoutAction.setShortcut('Ctrl++')
        self.zoomoutAction.setStatusTip("Zoom Out")
        self.zoomoutAction.setEnabled(False)
        self.zoomoutAction.triggered.connect(self.zoomout)

        self.fittowindowAction = QAction(QIcon.fromTheme('zoom-fit-best'), 'Fit to window', self)
        self.fittowindowAction.setShortcut('Ctrl+F')
        self.fittowindowAction.setStatusTip("Fit to window")
        self.fittowindowAction.setEnabled(False)
        self.fittowindowAction.triggered.connect(self.fittowindow)
        
        self.aboutAct = QAction("&About", self)
        self.aboutAct.setStatusTip("Show the application's About box")
        self.aboutAct.triggered.connect(self.about)

        self.aboutQtAct = QAction("About &Qt", self)
        self.aboutQtAct.setStatusTip("Show the Qt library's About box")
        self.aboutQtAct.triggered.connect(QApplication.aboutQt)

        # Status bar        
        self.statusBar()

        # Menu Bar        
        menubar = self.menuBar()
        fileMenu = menubar.addMenu('&File')
        aboutMenu = menubar.addMenu('&About')
        
        fileMenu.addAction(self.openAction)
        fileMenu.addAction(self.exitAction)

        aboutMenu.addAction(self.aboutAct)
        aboutMenu.addAction(self.aboutQtAct)

        # Tool Bar
        toolbar = self.addToolBar('Tools')                

        toolbar.addAction(self.openAction)
        toolbar.addAction(self.fittowindowAction)
        toolbar.addAction(self.zoominAction)
        toolbar.addAction(self.zoomoutAction)        

        # Image Label    
        self.simage = SelectableImage(self)
        self.simage.setBackgroundRole(QPalette.Base)
        self.simage.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.simage.setScaledContents(True)

        # Scroll Area
        self.scrollArea = QScrollArea(self)
        self.scrollArea.setBackgroundRole(QPalette.Dark)
        self.scrollArea.setWidget(self.simage)
        self.scrollArea.setVisible(False)

        # LCD Label
        self.lcdlabel = QLabel("Scale from 0 to 180")
        self.lcdlabel.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        
        # LCD Number
        self.lcd = QLCDNumber(self)
        self.lcd.display(0)

        # Color Widget & Palette
        self.colorw = QLabel(self)
        self.colorw.setFrameStyle(QFrame.Box | QFrame.Raised)
        self.palette = QPalette()
        self.palette.setColor(QPalette.Background, QColor(255, 255, 255))
        self.colorw.setPalette(self.palette)
        self.colorw.setAutoFillBackground(True)

        # Color scale
        self.scale = ScaleWidget(self)
        
        # Grid Container
        self.gridc = QWidget(self)
        self.gridc.setMaximumWidth(300)        
        self.gridc.setVisible(False)
        
        # Grid Layout
        self.grid = QGridLayout(self.gridc)
        self.grid.addWidget(self.lcdlabel, 0, 0)
        self.grid.addWidget(self.lcd, 1, 0)
        self.grid.addWidget(self.colorw, 2, 0)
        self.grid.addWidget(self.scale, 3, 0)
        
        # Splitter
        self.splitter = QSplitter(self)
        self.splitter.setOrientation(Qt.Horizontal)
        self.splitter.addWidget(self.gridc)
        self.splitter.addWidget(self.scrollArea)

        self.setCentralWidget(self.splitter)

        # Connect signals & slots
        self.simage.hueCalculated.connect(self.lcd.display)
        self.simage.hueCalculated.connect(self.updateColor)
        self.simage.hueCalculated.connect(self.scale.updatePointer)
        self.simage.hueCalculated.connect(self.logValue)
        
        self.setGeometry(300, 300, 300, 200)
        self.setWindowTitle('O3METER')    
        self.show()
        
##
# Main
#
if __name__ == '__main__':    
    app = QApplication(sys.argv)
    ex = MainWindow()
    sys.exit(app.exec_())  
