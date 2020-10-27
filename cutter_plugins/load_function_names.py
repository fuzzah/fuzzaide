
r"""
LoadFNames - Cutter plugin to load function names from file.
Expected file format (per line): hex_address function_name
Where:
hex_address is RVA aka offset from base address of a module.
        It should not start with "0x" nor it should end with "h"
function_name should not contain ::, return value, prefixes,
        arguments list etc etc: only names are allowed.
        For class methods you can substitute :: for __
 
Example of DUMPBIN-generated map file 'preprocessing':
  demumble < input.map > output.demumbled
  cat output.demumbled | sed -nr "s|^ 0001\:.{8} +([^ ].*) +([0-9a-fA-F]{16}) f +.*$|\1 \2|gp" | sed -r "s|::|__|g" | sed -r "s|\(.*?\)||g" | sed "s|:||g" | sed -r "s|^.+ (\w+\s+\w+)$|\1|g" | sed -r "s|^(\w+)\s+(\w+)|\2 \1|g" | sort > output.proc_addr
"""

import cutter

from PySide2.QtCore import QObject, SIGNAL
from PySide2.QtWidgets import QAction, QLabel, QWidget
from PySide2.QtWidgets import QPushButton, QFileDialog, QGridLayout, QLineEdit



class LoadFNamesDockWidget(cutter.CutterDockWidget):
    def __init__(self, parent, action):
        super(LoadFNamesDockWidget, self).__init__(parent, action)
        self.setObjectName("LoadFNames")
        self.setWindowTitle("LoadFNames")

        self.fname = None
        
        self.widget = QWidget(self)
        layout = QGridLayout()

        self.lbl_ba_desc = QLabel("enter base address of mapped binary")
        self.txt_baseaddr = QLineEdit("0x00000000")
        layout.addWidget(self.lbl_ba_desc,1,1,1,1)
        layout.addWidget(self.txt_baseaddr,1,2,1,1)
        
        self.lbl_path = QLabel("pick a file in format: hex_address func_name")
        self.btn_open = QPushButton("...")
        #self.btn_open.setFixedWidth(30)
        self.btn_open.clicked.connect(self.btn_open_click)
        layout.addWidget(self.lbl_path,2,1,1,1)
        layout.addWidget(self.btn_open,2,2,1,1)

        self.btn_go = QPushButton("name functions by addresses")
        layout.addWidget(self.btn_go,3,1,1,2)
        self.btn_go.clicked.connect(self.btn_go_click)

        self.widget.setLayout(layout)
        self.setWidget(self.widget)
    
    def btn_open_click(self):
        fileName, _ = QFileDialog.getOpenFileName(self,"pick a file in format: hex_address func_name", "","All Files (*)")
        if fileName:
            self.lbl_path.setText(fileName)
            self.fname = fileName
    
    def btn_go_click(self):
        if self.fname is not None:
            cutter.message(f"Opening file '{self.fname}'")
            try:
                data = []
                with open(self.fname, 'r', encoding='utf-8') as f:
                    data = f.read().split("\n")
                
                data = list(filter(lambda x: len(x) > 0, data))
                if len(data) < 1:
                    cutter.message("WARNING: no functions loaded from file")
                    cutter.message("No functions defined/renamed")
                    return

                ba = self.txt_baseaddr.text()

                try:
                    ba = int(ba,16) if ba.startswith('0x') else int(ba)
                except:
                    cutter.message("ERROR: incorrect base address")
                    cutter.message("No functions defined/renamed")
                    return

                def mapf(s):
                    t = s.split(' ')
                    return ba + int(t[0],16), t[1]
                
                data = list(map(mapf, data))

                data_t = list(map(list, zip(*data)))

                warned = {}
                for addr in data_t[0]:
                    if not warned.get(addr, False) and data_t[0].count(addr) > 1:
                        cutter.message(f"WARNING: multiple names given for address {hex(addr)}. " \
                            f"Skipping them ALL: {', '.join([x[1] for x in filter(lambda t: t[0] == addr, data)])}")
                        data = list(filter(lambda t: t[0] != addr, data))
                        warned[addr] = True
                
                if len(data) < 1:
                    cutter.message("WARNING: no functions left after checking for duplicate addresses")
                    cutter.message("No functions defined/renamed")
                    return
                
                for addr, name in data:
                    cutter.message(f"Naming {hex(addr)} '{name}'")
                    #cutter.core().renameFunction(addr, name) # doesn't seem to tell if no such function found
                    cutter.core().createFunctionAt(addr, name) # seems to not care about existing functions, thus renaming it
                
                cutter.message(f"Defined/renamed {len(data)} functions from file {self.fname}")

                """
                related functions:
                RAnalFunction *functionAt(ut64 addr)
                QString createFunctionAt(RVA addr, QString name)
                void renameFunction(const RVA offset, const QString &newName)
                """

            except Exception as e:
                cutter.message(f"Error: {e}")


class LoadFNamesPlugin(cutter.CutterPlugin):
    name = "LoadFNames"
    description = "This plugin loads addresses and function names from user provided file" \
        " and then defines these functions in loaded binary at specified offset"
    version = "1.0"
    author = "fuzzah"

    def setupPlugin(self):
        pass

    def setupInterface(self, main):
        action = QAction("LoadFNames", main)
        action.setCheckable(True)
        widget = LoadFNamesDockWidget(main, action)
        main.addPluginDockWidget(widget, action)

    def terminate(self):
        pass

def create_cutter_plugin():
    return LoadFNamesPlugin()