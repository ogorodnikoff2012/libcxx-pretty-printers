set pagination off
set confirm off

python
import os, sys, gdb

sys.path.insert(0, os.environ["PRINTER_PATH"])
from libcxx.v1.printers import register_libcxx_printers
register_libcxx_printers(None)

class BreakHereHandler(gdb.Breakpoint):
    def stop(self):
        frame = gdb.selected_frame()
        tag = frame.read_var("tag").string()
        caller = frame.older()
        gdb.write("@@@ TAG: " + tag + "\n")
        try:
            caller.select()
            val = gdb.execute("output v", to_string=True)
            gdb.write("@@@ PRINT: " + val + "\n")
        except Exception as e:
            gdb.write("@@@ ERROR: " + str(e) + "\n")
        return False

BreakHereHandler("BREAK_HERE")
end

run
quit
