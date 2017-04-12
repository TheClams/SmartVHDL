# Some util function linked directly to sublime

import sublime, sublime_plugin
import re, string, os

#filename can be in a unix specific format => convert to windows if needed
def normalize_fname(fname):
    if sublime.platform() == 'windows':
        fname= re.sub(r'/([A-Za-z])/(.+)', r'\1:/\2', fname)
        fname= re.sub(r'/', r'\\', fname)
    return fname

def find_closest(view, r, re_str):
    nl = []
    ra = view.find_all(re_str,0,r'\1',nl)
    v = ''
    if ra:
        for (rf,n) in zip(ra,nl):
            if rf.a < r.a:
                v = n
            else:
                break
    # print('[sublime_util.find_closest] Regexp = "{}"\n\t => {} at {}. Loc is {} => {}'.format(re_str,nl,ra,r.a,v))
    return v

# Create a panel and display a text
def print_to_panel(txt,name):
    window = sublime.active_window()
    v = window.create_output_panel(name)
    v.run_command('append', {'characters': txt})
    window.run_command("show_panel", {"panel": "output."+name})

# Move cursor to the beginning of a region
def move_cursor(view,pos):
    view.sel().clear()
    view.sel().add(sublime.Region(pos,pos))
    view.show_at_center(pos)
