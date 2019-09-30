# Some util function linked directly to sublime

import sublime, sublime_plugin
import re, string, os

#filename can be in a unix specific format => convert to windows if needed
def normalize_fname(fname):
    if sublime.platform() == 'windows':
        fname= re.sub(r'/([A-Za-z])/(.+)', r'\1:/\2', fname)
        fname= re.sub(r'/', r'\\', fname)
    return fname

#Expand a region to a given scope
def expand_to_scope(view, scope_name, region):
    r_tmp = region
    # print('Init region = ' + str(r_tmp) + ' => text = ' + view.substr(region))
    #Expand forward line by line until scope does not match or end of file is reached
    p = region.b
    scope = view.scope_name(p)
    while scope_name in scope:
        region.b = p
        p = view.find_by_class(p,True,sublime.CLASS_LINE_END)
        scope = view.scope_name(p)
        if p <= region.b:
            break
    # print('Forward line done:' + str(p))
    # Retract backward until we find the scope back
    while scope_name not in scope and p>region.b:
        p=p-1
        scope = view.scope_name(p)
    region.b = p+1
    # print('Retract done:' + str(p) + ' => text = ' + view.substr(region))
    #Expand backward word by word until scope does not match or end of file is reached
    p = region.a
    scope = view.scope_name(p)
    while scope_name in scope:
        region.a = p
        p = view.find_by_class(p,False,sublime.CLASS_LINE_START)
        scope = view.scope_name(p-1)
        if p >= region.a:
            break
    # print('Backward line done:' + str(p))
    # Retract forward until we find the scope back
    while scope_name not in scope and p<region.a:
        p=p+1
        scope = view.scope_name(p)
    if view.classify(p) & sublime.CLASS_LINE_START == 0:
        region.a = p-1
    # print('Retract done:' + str(p) + ' => text = ' + view.substr(region))
    # print(' Selected region = ' + str(region) + ' => text = ' + view.substr(region))
    return region


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

# Find the file and row/col where a symbol is defined, using a regexp to confirm
def lookup_symbol(view, name, re_str):
    info = {'fname':'','row':-1,'col':-1,'match':None}
    flist = view.window().lookup_symbol_in_index(name)
    if flist:
        # Check if module is defined in current file first
        fname = view.file_name()
        flist_norm = [normalize_fname(f[0]) for f in flist]
        if fname in flist_norm:
            flines = view.substr(sublime.Region(0, view.size()))
            info['match'] = re.search(re_str,flines,flags=re.MULTILINE)
            info['fname'] = flist[flist_norm.index(fname)][0]
            info['row'  ] = flist[flist_norm.index(fname)][2][0]
            info['col'  ] = flist[flist_norm.index(fname)][2][1]
        # Check all file in list if not in the current file
        if not info['match'] :
            for i,f in enumerate(flist):
                info['fname'] = flist_norm[i]
                with open(info['fname']) as file:
                    flines = file.read()
                info['match'] = re.search(re_str,flines,flags=re.MULTILINE)
                # Stop when match succeed
                if info['match']:
                    info['row'  ] = f[2][0]
                    info['col'  ] = f[2][1]
                    break
    return info

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

#
def goto_index_symbol(view,name):
    w = view.window()
    filelist = w.lookup_symbol_in_index(name)
    if not filelist:
        # print('[SystemVerilog] Unable to find "{}"'.format(name))
        return None,''
    # Select first
    fnorm = normalize_fname(filelist[0][0])
    v = view.window().find_open_file(fnorm)
    if v:
        w.focus_view(v)
        # print('View already open : {}'.format(v.id()))
        return v,''
    fname = '{}:{}:{}'.format(filelist[0][0],filelist[0][2][0],filelist[0][2][1])
    w.focus_view(view)
    v = w.open_file(fname,sublime.ENCODED_POSITION)
    w.focus_view(v)
    return v,filelist[0][0]

# Move cursor to a symbol with a known filename
def goto_symbol_in_file(view,sname,fname):
    w = view.window()
    filelist = w.lookup_symbol_in_index(sname)
    flist_norm = [normalize_fname(f[0]) for f in filelist]
    if fname in flist_norm:
        _,_,rowcol = filelist[flist_norm.index(fname)]
        w.focus_view(view)
        if fname == view.file_name():
            move_cursor(view,view.text_point(rowcol[0]-1,rowcol[1]-1))
        else :
            fname += ':{}:{}'.format(rowcol[0],rowcol[1])
            w.open_file(fname,sublime.ENCODED_POSITION)
