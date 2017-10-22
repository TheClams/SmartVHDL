import sublime, sublime_plugin
import re, string, os, sys, functools, mmap, pprint, imp, threading
from collections import Counter
from plistlib import readPlistFromBytes

try:
    from .util import vhdl_util
    from .util import sublime_util
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), "util"))
    import vhdl_util
    import sublime_util

############################################################################
# Init
tooltip_css = ''
tooltip_flag = 0
pluginDir = 'Smart VHDL'

def plugin_loaded():
    imp.reload(vhdl_util)
    imp.reload(sublime_util)
    # Ensure the preference settings are properly reloaded when changed
    global pref_settings
    pref_settings = sublime.load_settings('Preferences.sublime-settings')
    pref_settings.clear_on_change('reload')
    pref_settings.add_on_change('reload',plugin_loaded)
    # Ensure the VHDL settings are properly reloaded when changed
    global vhdl_settings
    vhdl_settings = sublime.load_settings('VHDL.sublime-settings')
    vhdl_settings.clear_on_change('reload')
    vhdl_settings.add_on_change('reload',plugin_loaded)
    global tooltip_flag
    if vhdl_settings.get('vhdl.tooltip_hide_on_move',True):
        tooltip_flag = sublime.HIDE_ON_MOUSE_MOVE_AWAY
    else:
        tooltip_flag = 0
    global pluginDir
    pluginDir = (os.path.split(os.path.dirname(__file__)))[1]
    init_css()

def init_css():
    global tooltip_css
    color_plist = readPlistFromBytes(sublime.load_binary_resource(pref_settings.get('color_scheme')))
    color_dict = {}
    for x in color_plist['settings'] :
        if 'scope' in x:
            for s in x['scope'].split(','):
                color_dict[s.strip()] = x['settings']
    color_dict['__GLOBAL__'] = color_plist['settings'][0]['settings'] # first settings contains global settings, without scope(hopefully)
    bg = int(color_dict['__GLOBAL__']['background'][1:],16)
    fg = int(color_dict['__GLOBAL__']['foreground'][1:],16)
    # Get color for keyword, support, storage, default to foreground
    kw  = fg if 'keyword' not in color_dict else int(color_dict['keyword']['foreground'][1:],16)
    sup = fg if 'support' not in color_dict else int(color_dict['support']['foreground'][1:],16)
    sto = fg if 'storage' not in color_dict else int(color_dict['storage']['foreground'][1:],16)
    ent = fg if 'entity' not in color_dict else int(color_dict['entity']['foreground'][1:],16)
    fct = fg if 'support.function' not in color_dict else int(color_dict['support.function']['foreground'][1:],16)
    op  = fg if 'keyword.operator' not in color_dict else int(color_dict['keyword.operator']['foreground'][1:],16)
    num = fg if 'constant.numeric' not in color_dict else int(color_dict['constant.numeric']['foreground'][1:],16)
    st  = fg if 'string' not in color_dict else int(color_dict['string']['foreground'][1:],16)
    # Create background and border color based on the background color
    b = bg & 255
    g = (bg>>8) & 255
    r = (bg>>16) & 255
    if b > 128:
        bgHtml = b - 0x33
        bgBody = b - 0x20
    else:
        bgHtml = b + 0x33
        bgBody = b + 0x20
    if g > 128:
        bgHtml += (g - 0x33)<<8
        bgBody += (g - 0x20)<<8
    else:
        bgHtml += (g + 0x33)<<8
        bgBody += (g + 0x20)<<8
    if r > 128:
        bgHtml += (r - 0x33)<<16
        bgBody += (r - 0x20)<<16
    else:
        bgHtml += (r + 0x33)<<16
        bgBody += (r + 0x20)<<16
    tooltip_css = 'html {{ background-color: #{bg:06x}; color: #{fg:06x}; }}\n'.format(bg=bgHtml, fg=fg)
    tooltip_css+= 'body {{ background-color: #{bg:06x}; margin: 1px; font-size: 1em; }}\n'.format(bg=bgBody)
    tooltip_css+= 'p {padding-left: 0.6em;}\n'
    tooltip_css+= '.content {margin: 0.8em;}\n'
    tooltip_css+= '.keyword {{color: #{c:06x};}}\n'.format(c=kw)
    tooltip_css+= '.support {{color: #{c:06x};}}\n'.format(c=sup)
    tooltip_css+= '.storage {{color: #{c:06x};}}\n'.format(c=sto)
    tooltip_css+= '.function {{color: #{c:06x};}}\n'.format(c=fct)
    tooltip_css+= '.entity {{color: #{c:06x};}}\n'.format(c=ent)
    tooltip_css+= '.operator {{color: #{c:06x};}}\n'.format(c=op)
    tooltip_css+= '.numeric {{color: #{c:06x};}}\n'.format(c=num)
    tooltip_css+= '.string {{color: #{c:06x};}}\n'.format(c=st)
    tooltip_css+= '.extra-info {font-size: 0.9em; }\n'

############################################################################
callbacks_on_load = {}

class VerilogOnLoadEventListener(sublime_plugin.EventListener):
    # Called when a file is finished loading.
    def on_load_async(self, view):
        global callbacks_on_load
        if view.file_name() in callbacks_on_load:
            callbacks_on_load[view.file_name()]()
            del callbacks_on_load[view.file_name()]

############################################################################
# Display type of the signal/variable under the cursor into the status bar #

# Event onHover to display the popup
class VhdlShowTypeHover(sublime_plugin.EventListener):
    def on_hover(self, view, point, hover_zone):
        # Popup only on text
        if hover_zone != sublime.HOVER_TEXT:
            return
        # Check file size to optionnaly disable the feature (finding the information can be quite long)
        threshold = view.settings().get('vhdl.hover_max_size',-1)
        if view.size() > threshold and threshold!=-1 :
            return
        # Only show a popup for vhdl, when not in a string of a comment
        scope = view.scope_name(point)
        if 'source.vhdl' not in scope:
            return
        if any(w in scope for w in ['comment', 'string', 'keyword']):
            return
        popup = VhdlTypePopup(view)
        sublime.set_timeout_async(lambda r=view.word(point), p=point: popup.show(r,p))

class VhdlTypePopup :
    def __init__(self,view):
        self.view = view

    def show(self,region,location):
        # If nothing is selected expand selection to word
        if region.empty() :
            region = self.view.word(region)
        # Make sure a whole word is selected
        elif (self.view.classify(region.a) & sublime.CLASS_WORD_START)==0 or (self.view.classify(region.b) & sublime.CLASS_WORD_END)==0:
            if (self.view.classify(region.a) & sublime.CLASS_WORD_START)==0:
                region.a = self.view.find_by_class(region.a,False,sublime.CLASS_WORD_START)
            if (self.view.classify(region.b) & sublime.CLASS_WORD_END)==0:
                region.b = self.view.find_by_class(region.b,True,sublime.CLASS_WORD_END)
        v = self.view.substr(region)
        # trigger on valid word only
        if not re.match(r'^[A-Za-z_]\w*$',v):
            return
        #
        s,ti = self.get_type(v,region)
        if not s:
            sublime.status_message('No definition found for ' + v)
        else :
            s = self.color_str(s,ti)
            s = '<style>{css}</style><div class="content">{txt}</div>'.format(css=tooltip_css, txt=s)
            self.view.show_popup(s,location=location, flags=tooltip_flag, max_width=500, on_navigate=self.on_navigate)

    def get_type(self,var_name,region):
        scope = self.view.scope_name(region.a)
        ti = None
        txt = ''
        if 'variable.parameter.port' in scope:
            if 'meta.block.entity_instantiation' in scope:
                r_inst = sublime_util.expand_to_scope(self.view,'meta.block.entity_instantiation',region)
            elif 'meta.block.component_instantiation' in scope:
                r_inst = sublime_util.expand_to_scope(self.view,'meta.block.component_instantiation',region)
            inst_txt = self.view.substr(r_inst)
            m = re.search(r'(?si)(?:(?P<scope>\w+)\.)?(?P<mname>\w+)\s+(?:port|generic)',inst_txt)
            if m:
                re_str = r'(?si)(?P<type>component|entity)\s+(?P<name>'+m.group('mname')+r')\s+is\s+(?P<content>.*?)\bend\s+((?P=type)|(?P=name))'
                info = sublime_util.lookup_symbol(self.view,m.group('mname'),re_str)
                # print('Port {} in module {} defined in {}'.format(var_name,m.group('mname'),info))
                # TODO: handle component
                if info['match']:
                    ti = vhdl_util.get_type_info(info['match'].group('content'),var_name)
                    if ti:
                        txt = ti['decl']
        else :
            # lookup for a signal/variable declaration in current file
            lines = self.view.substr(sublime.Region(0, self.view.line(region).b))
            ti = vhdl_util.get_type_info(lines,var_name)
            if ti:
                txt = ti['decl']
        return txt,ti

    def color_str(self,s, addLink=False, ti_var=None):
        # Split all text in word, special character, space and line return
        words = re.findall(r"\w+|[^\w\s]|\s+", s)
        # print('String = "{}" \n Split => {}'.format(s,words))
        sh = ''
        idx_type = -1
        if words[0].lower() in ['signal','variable','constant']:
            idx_type = 6
        elif words[0] in ['port']:
            idx_type = 8
        for i,w in enumerate(words):
            # Check for keyword
            if w.lower() in ['signal','port','constant','array','downto','upto','of','in','out','inout']:
                sh+='<span class="keyword">{0}</span>'.format(w)
            elif w in [':','-','+','=']:
                sh+='<span class="operator">{0}</span>'.format(w)
            elif re.match(r'\d+',w):
                sh+='<span class="numeric">{0}</span>'.format(w)
            # Type
            elif i==idx_type:
                sh+='<span class="storage">{0}</span>'.format(w)
            # Unknown words/characters => copy as-is
            elif not w.strip() :
                sh += ' '
            # Reduce multiple spaces to just one
            else :
                sh += w

        return sh

    def on_navigate(self, href):
        href_s = href.split('@')
        pos = sublime.Region(0,0)
        v = self.view.window().open_file(href_s[1], sublime.ENCODED_POSITION)


############################################################################
# Helper function to retrieve current module name based on cursor position #

def getModuleName(view):
    r = view.sel()[0]
    # Empty selection ? get current module name
    if r.empty():
        re_str = r'(?is)^[ \t]*(?:entity|architecture\s+\w+\s+of)\s+(\w+\b)'
        mname = sublime_util.find_closest(view,r,re_str)
    else:
        mname = view.substr(r)
    return mname

###############################################################
# Create a new buffer showing the hierarchy of current module #
hierarchyInfo = {'dict':{}, 'view':None,'fname':'', 'name':''}
hierarchyView = None

class VhdlShowHierarchyCommand(sublime_plugin.TextCommand):

    def run(self,edit):
        mname = getModuleName(self.view)
        if not mname:
            print('[VHDL.navigation] No entity/architecture found !')
            return
        txt = self.view.substr(sublime.Region(0, self.view.size()))
        inst_l = vhdl_util.get_inst_list(txt,mname)
        if not inst_l:
            print('[VHDL.navigation] No hierarchy found !')
            return
        sublime.status_message("Show Hierarchy can take some time, please wait ...")
        sublime.set_timeout_async(lambda inst_l=inst_l, w=self.view.window(), mname=mname : self.showHierarchy(w,inst_l,mname))

    def showHierarchy(self,w,inst_l,mname):
        # Save info in global for later access
        global hierarchyInfo
        global pluginDir
        hierarchyInfo['dict'] = {}
        hierarchyInfo['view'] = self.view
        hierarchyInfo['fname'] = self.view.file_name()
        hierarchyInfo['name'] = mname
        # Create Dictionnary where each type is associated with a list of tuple (instance type, instance name)
        self.d = {}
        self.d[mname] = inst_l
        self.unresolved = []
        self.component = []
        li = list(set(inst_l))
        while li:
            li_next = []
            for i in li:
                inst_type = i[1]
                if inst_type not in hierarchyInfo['dict'].keys() and inst_type not in self.component:
                    filelist = w.lookup_symbol_in_index(inst_type)
                    filelist = list(set([f[0] for f in filelist]))
                    # print('Symbol {} defined in {}'.format(inst_type,[x[0] for x in filelist]))
                    i_il = []
                    if filelist:
                        for f in filelist:
                            fname = sublime_util.normalize_fname(f)
                            i_il = vhdl_util.get_inst_list_from_file(fname,inst_type)
                            if i_il is not None:
                                hierarchyInfo['dict'][inst_type] = fname
                                break
                    else :
                        self.unresolved.append(inst_type)
                    if i_il:
                        li_next += i_il
                        self.d[inst_type] = i_il
                    elif i_il is None :
                        self.component.append(inst_type)
            li = list(set(li_next))
        txt = mname + '\n'
        txt += self.printSubmodule(mname,1)

        # Check if we open the result in a new window
        if self.view.settings().get('vhdl.hierarchy_new_window',False):
            sublime.run_command('new_window')
            w = sublime.active_window()

        v = w.new_file()
        v.settings().set("tab_size", 2)
        v.set_name(mname + ' Hierarchy')
        v.set_syntax_file('Packages/{}/Find Results VHDL.hidden-tmLanguage'.format(pluginDir))
        v.set_scratch(True)
        v.run_command('insert_snippet',{'contents':str(txt)})

    def printSubmodule(self,name,lvl):
        txt = ''
        if name in self.d:
            # print('printSubmodule ' + str(self.d[name]))
            for x in self.d[name]:
                txt += '  '*lvl
                if x[1] in self.d :
                    txt += '+ {name}    ({type})\n'.format(name=x[0],type=x[1])
                    if lvl<20 :
                        txt += self.printSubmodule(x[1],lvl+1)
                else:
                    if x[1] in self.unresolved:
                        comment = '  [U]'
                    elif x[1] in self.component:
                        comment = '  [C]'
                    else:
                        comment = ''
                    txt += '- {name}    ({type}){comment}\n'.format(name=x[0],type=x[1],comment=comment)
        return txt


# Navigate within the hierarchy
class VhdlHierarchyGotoDefinitionCommand(sublime_plugin.TextCommand):

    def run(self,edit):
        global hierarchyInfo
        r = self.view.sel()[0]
        if r.empty() :
            r = self.view.word(r)
        scope = self.view.scope_name(r.a)
        fname = ''
        module_name = self.view.substr(r)
        inst_name = ''
        # Not in the proper file ? use standard goto_definition to
        if 'text.result-vhdl' not in scope:
            self.view.window().run_command('goto_definition')
            return
        if 'entity.name' in scope:
            l = self.view.substr(self.view.line(r))
            indent = (len(l) - len(l.lstrip()))-2
            if indent<0:
                print('[VHDL.navigation] Hierarchy buffer corrupted : Invalid position for an instance !')
                return
            elif indent == 0:
                inst_name = module_name
                module_name = hierarchyInfo['name']
                fname = hierarchyInfo['fname']
            else:
                w = ''
                # find module parent name
                txt = self.view.substr(sublime.Region(0,r.a))
                m = re.findall(r'^{}\+ \w+\s+\((\w+)\)'.format(' '*indent),txt,re.MULTILINE)
                if m:
                    inst_name = module_name
                    module_name = m[-1]
                    if module_name in hierarchyInfo['dict']:
                        fname = hierarchyInfo['dict'][module_name]
        elif 'storage.name' in scope:
            if module_name in hierarchyInfo['dict']:
                fname = hierarchyInfo['dict'][module_name]
        elif 'keyword.module' in scope:
            module_name = hierarchyInfo['name']
            fname = hierarchyInfo['fname']

        # print('Module={} instance={} (scope={}) => filename = {}'.format(module_name,inst_name,scope,fname))
        if fname:
            v = hierarchyInfo['view'].window().find_open_file(fname)
            if v :
                hierarchyInfo['view'].window().focus_view(v)
                self.goto_symb(v,module_name,inst_name)
            else :
                v = hierarchyInfo['view'].window().open_file(fname)
                global callbacks_on_load
                callbacks_on_load[fname] = lambda v=v, module_name=module_name, inst_name=inst_name: self.goto_symb(v,module_name,inst_name)
        else :
            self.view.window().run_command('goto_definition')

    def goto_symb(self,v,module_name,inst_name):
        global hierarchyInfo
        row=-1
        if inst_name :
            # Find instance symbol position
            #print('[VHDL.navigation] Looking for instance {} in {}'.format(inst_name,v.symbols()))
            for x in v.symbols() :
                if x[1] == inst_name:
                    row,col = v.rowcol(x[0].a)
                    #print('[VHDL.navigation] Found at {}:{}'.format(row,col))
                    break
        else :
            # Find architecture symbol position
            #print('L[VHDL.navigation] ooking for architecture of {} in {}'.format(module_name,v.symbols()))
            for x in v.symbols() :
                if x[1].startswith(module_name+' :'):
                    row,col = v.rowcol(x[0].a)
                    # print('Found at {}:{}'.format(row,col))
                    break
        if row>=0:
            sublime_util.move_cursor(v,v.text_point(row,col))
