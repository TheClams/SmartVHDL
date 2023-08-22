from __future__ import absolute_import

import sublime, sublime_plugin
import re, string, os, sys, functools, mmap, pprint, imp, threading
from collections import Counter
from plistlib import readPlistFromBytes

try:
    from . import vhdl_module
    from .util import vhdl_util
    from .util import sublime_util
    from .color_scheme_util import st_color_scheme_matcher
    from .color_scheme_util import rgba
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), "util"))
    import vhdl_util
    import sublime_util
    sys.path.append(os.path.join(os.path.dirname(__file__), "color_scheme_util"))
    import st_color_scheme_matcher
    import rgba

############################################################################
# Init
default_type = [
    'bit', 'bit_vector', 'boolean', 'character', 'integer', 'natural', 'positive', 'real', 'string',
    'std_logic', 'std_ulogic', 'std_logic_vector', 'std_ulogic_vector', 'signed', 'unsigned'
]
tooltip_css = ''
tooltip_flag = 0
show_ref = True
colors = {}

def plugin_loaded():
    imp.reload(vhdl_util)
    imp.reload(sublime_util)
    imp.reload(st_color_scheme_matcher)
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
    global show_ref
    show_ref = int(sublime.version()) >= 3145 and vhdl_settings.get('vhdl.tooltip_show_refs',True)
    init_css()

def init_css():
    global tooltip_css
    scheme = st_color_scheme_matcher.ColorSchemeMatcher(pref_settings.get('color_scheme'))
    bg = scheme.get_special_color('background')
    fg = scheme.get_special_color('foreground')
    # Create background and border color based on the background color
    bg_rgb = rgba.RGBA(bg)
    if bg_rgb.b > 128:
        bgHtml = bg_rgb.b - 0x33
        bgBody = bg_rgb.b - 0x20
    else:
        bgHtml = bg_rgb.b + 0x33
        bgBody = bg_rgb.b + 0x20
    if bg_rgb.g > 128:
        bgHtml += (bg_rgb.g - 0x33)<<8
        bgBody += (bg_rgb.g - 0x20)<<8
    else:
        bgHtml += (bg_rgb.g + 0x33)<<8
        bgBody += (bg_rgb.g + 0x20)<<8
    if bg_rgb.r > 128:
        bgHtml += (bg_rgb.r - 0x33)<<16
        bgBody += (bg_rgb.r - 0x20)<<16
    else:
        bgHtml += (bg_rgb.r + 0x33)<<16
        bgBody += (bg_rgb.r + 0x20)<<16
    tooltip_css = 'html {{ background-color: #{bg:06x}; color: {fg}; }}\n'.format(bg=bgHtml, fg=fg)
    tooltip_css+= 'body {{ background-color: #{bg:06x}; margin: 1px; font-size: 1em; }}\n'.format(bg=bgBody)
    tooltip_css+= 'p {padding-left: 0.6em;}\n'
    tooltip_css+= '.content {margin: 0.8em;}\n'
    tooltip_css+= 'h1 {font-size: 1.0rem;font-weight: bold; margin: 0 0 0.25em 0;}\n'
    tooltip_css+= 'a {{color: {c};}}\n'.format(c=fg)
    tooltip_css+= '.keyword {{color: {c};}}\n'.format(c=scheme.get_color('keyword'))
    tooltip_css+= '.support {{color: {c};}}\n'.format(c=scheme.get_color('support'))
    tooltip_css+= '.storage {{color: {c};}}\n'.format(c=scheme.get_color('storage'))
    tooltip_css+= '.function {{color: {c};}}\n'.format(c=scheme.get_color('support.function'))
    tooltip_css+= '.entity {{color: {c};}}\n'.format(c=scheme.get_color('entity'))
    tooltip_css+= '.operator {{color: {c};}}\n'.format(c=scheme.get_color('keyword.operator'))
    tooltip_css+= '.numeric {{color: {c};}}\n'.format(c=scheme.get_color('constant.numeric'))
    tooltip_css+= '.string {{color: {c};}}\n'.format(c=scheme.get_color('string'))
    tooltip_css+= '.extra-info {font-size: 0.9em; }\n'
    tooltip_css+= '.ref_links {font-size: 0.9em; color: #0080D0; padding-left: 0.6em}\n'
    global colors
    colors['operator'] = scheme.get_color('keyword.operator')


############################################################################
# Help function to retrieve type

def type_info(view, t, region):
    if region:
        pos = view.line(region).b
    else:
        pos = self.view.size()
    txt = view.substr(sublime.Region(0, pos))
    tti = vhdl_util.get_type_info(txt,t,4)
    if not tti or not tti['type']:
        filelist = view.window().lookup_symbol_in_index(t)
        if filelist:
            file_ext = ('vhd','vhdl')
            # file_ext = tuple(self.settings.get('vhdl.ext',['vhd','vhdl']))
            file_checked = []
            for f in filelist:
                fname = sublime_util.normalize_fname(f[0])
                if fname in file_checked:
                    continue
                file_checked.append(fname)
                if fname.lower().endswith(file_ext):
                    # print(v + ' of type ' + t + ' defined in ' + str(fname))
                    tti = vhdl_util.get_type_info_file(fname,t,4)
                    if tti['type']:
                        tti['fname'] = (f[0],f[2][0],f[2][1])
                        # print(tti['fname'])
                        break
    # print(['[type_info] tti={}'.format(tti)])
    return tti

def type_info_on_hier(view, varname, txt=None, region=None):
    va = varname.split('.')
    ti = None
    scope = ''
    if not txt and region:
        txt = view.substr(sublime.Region(0, view.line(region).b))
    for i in range(0,len(va)):
        v = va[i].split('[')[0] # retrieve name without array part
        # Get type definition: first iteration is done inside current file
        if i==0:
            ti = vhdl_util.get_type_info(txt, v,4)
            # print('[type_info_on_hier] level {} : {} has type {}'.format(i,v,ti['type']))
        elif ti and ti['type']:
            ti = type_info(view,ti['type'],region)
            # print('[type_info_on_hier] level {} : {} has type {}'.format(i,v,ti['type']))
            if ti and ti['type']=='record' :
                fti = vhdl_util.get_all_type_info_from_record(ti['decl'])
                line = 0 if 'fname' not in ti else ti['fname'][1]+1
                for f in fti:
                    if f['name'].lower()==v.lower():
                        if 'fname' in ti:
                            f['fname'] = (ti['fname'][0],line,ti['fname'][2])
                        ti = f
                        break
                    line += 1

    return ti

############################################################################
callbacks_on_load = {}

class VhdlOnLoadEventListener(sublime_plugin.EventListener):
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
        # Extends to parent if previous character is a dot
        while region.a>1 and self.view.substr(sublime.Region(region.a-1,region.a))=='.' :
            c = self.view.substr(sublime.Region(region.a-2,region.a-1))
            # Array selection -> extend to start of array
            if c == ')':
                region.a = self.view.find_by_class(region.a-3,False,sublime.CLASS_WORD_START)
            if self.view.classify(region.a-2) & sublime.CLASS_WORD_START:
                region.a = region.a-2
            else :
                region.a = self.view.find_by_class(region.a-2,False,sublime.CLASS_WORD_START)

        v = self.view.substr(region)
        # print('[VhdlTypePopup] Var = {}'.format(v))
        # trigger on valid word only
        # if not re.match(r'^[A-Za-z_]\w*$',v):
        #     return
        #
        s,ti = self.get_type(v,region)
        if not s:
            sublime.status_message('No definition found for ' + v)
        else :
            ref_name = ''
            s = self.color_str(s,True,ti)
            if ti and ti['type'] in ['entity', 'component']:
                ref_name = ti['name']
            # Records: add field definition
            if ti['type'] and ti['tag']:
                type_base= ti['type'].split('(')[0].lower()
                if ti['tag'] in ['signal','port'] and type_base not in default_type:
                    tti = type_info(self.view,ti['type'],region)
                    if tti and tti['type'] == 'record' :
                        fti = vhdl_util.get_all_type_info_from_record(tti['decl'])
                        template='<br><span class="extra-info">{0}{1}</span>'
                        for f in fti:
                            x = self.color_str(f['decl'])
                            s += template.format('&nbsp;'*4,x)
            # Add reference list
            if show_ref and ref_name :
                refs = self.view.window().lookup_references_in_index(ref_name)
                if refs:
                    ref_links = []
                    for l in refs :
                        l_href = '{}:{}:{}'.format(l[0],l[2][0],l[2][1])
                        l_name = os.path.basename(l[0])
                        ref_links.append('<a href="LINK@{}" class="ref_links">{}</a>'.format(l_href,l_name))
                    s += '<h1><br>Reference:</h1><span>{}</span>'.format('<br>'.join(ref_links))
            # Create popup
            s = '<style>{css}</style><div class="content">{txt}</div>'.format(css=tooltip_css, txt=s)
            self.view.show_popup(s,location=location, flags=tooltip_flag, max_width=500, on_navigate=self.on_navigate)

    def get_type(self,var_name,region):
        scope = self.view.scope_name(region.b-1)
        ti = None
        txt = ''
        # print('[VhdlTypePopup:get_type] Var={}, region={}, scope={}'.format(var_name,region,scope))
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
                    ti = vhdl_util.get_type_info(info['match'].group('content'),var_name,4)
                    if ti:
                        txt = ti['decl']
        elif 'entity.name.type.entity' in scope or 'entity.name.type.component' in scope:
            t = 'component' if 'component' in scope else 'entity'
            ti = {'decl': '{} {}'.format(t,var_name), 'type':t, 'name':var_name, 'tag':'decl', 'value':None}
            txt = ti['decl']
        elif 'storage.type.entity.reference' in scope or 'storage.type.component.reference' in scope:
            t = 'component' if 'component' in scope else 'entity'
            ti = {'decl': '{} {}'.format(t,var_name), 'type':t, 'name':var_name, 'tag':'reference', 'value':None}
            txt = ti['decl']
        elif 'storage.type.userdefined' in scope :
            ti = type_info(self.view,var_name,region)
            if ti:
                txt = ti['decl']
                if ti['type'] == 'record' :
                    txt = re.sub(r'(\brecord\b|;)',r'\1<br>',txt)
        elif '.' in var_name:
            ti = type_info_on_hier(self.view, var_name, region=region)
            if ti:
                txt = ti['decl']
        else :
            # lookup for a signal/variable declaration in current file
            lines = self.view.substr(sublime.Region(0, self.view.line(region).b))
            ti = vhdl_util.get_type_info(lines,var_name,4)
            if ti:
                txt = ti['decl']
        return txt,ti

    def color_str(self,s, addLink=False, ti_var=None):
        # Split all text in word, special character, space and line return
        words = re.findall(r"\w+|<<|>>|[^\w\s]|\s+", s)
        # print('[color_str] String = "{}" \n Split => {}\n ti = {}'.format(s,words,ti_var))
        # print(ti_var)
        sh = ''
        idx_type = -1
        link = ''
        if words[0].lower() in ['signal','variable','constant','alias']:
            idx_type = 6
            link = 'LOCAL@{}:{}'.format(words[0],words[2])
        elif words[0] in ['port']:
            idx_type = 8
            link = 'LOCAL@{}:{}'.format(words[0],words[2])
        elif ti_var :
            if ti_var['tag']=='reference' :
                re_str = r'(?si)(?P<type>entity)\s+(?P<name>'+ti_var['name']+r')\s+is'
                info = sublime_util.lookup_symbol(self.view, ti_var['name'], re_str)
                link = 'LINK@{}:{}:{}'.format(info['fname'],info['row'],info['col'])
            elif ti_var['tag']=='generic':
                idx_type = 4
                sh+='<span class="keyword">generic</span> '
                link = 'LOCAL@{}:{}'.format(words[0],words[2])
            elif 'fname' in ti_var:
                link = 'LINK@{}:{}:{}'.format(ti_var['fname'][0],ti_var['fname'][1],ti_var['fname'][2])
        for i,w in enumerate(words):
            # Check for keyword
            if w.lower() in ['signal','variable','constant','port', 'type', 'is','end', 'record','array','downto','to','of','in','out','inout','entity','component','alias']:
                sh+='<span class="keyword">{0}</span>'.format(w)
            elif w in [':','-','+','=']:
                sh+='<span class="operator">{0}</span>'.format(w)
            elif w in ['<<','>>']:
                wt = '&lt;&lt;' if w=='<<' else '&gt;&gt;'
                sh+='<span class="operator">{0}</span>'.format(wt)
            elif re.match(r'\d+',w):
                sh+='<span class="numeric">{0}</span>'.format(w)
            # Type
            elif i==idx_type or w.lower() in default_type:
                sh+='<span class="storage">{0}</span>'.format(w)
            # Variable name
            elif addLink and ti_var and link and w==ti_var['name']:
                sh+='<a href="{}">{}</a>'.format(link,w)
            # Unknown words/characters => copy as-is
            elif not w.strip() :
                sh += ' '
            # Reduce multiple spaces to just one
            else :
                sh += w

        return sh

    def on_navigate(self, href):
        href_s = href.split('@')
        # print(href_s)
        if href_s[0] == 'LOCAL':
            ws = href_s[1].split(':')
            if ws[0] == 'port' :
                s = r'(?si)\b{}\b(,[\w\s,]+)?\s*:\s*(in|out)'.format(ws[1])
            else :
                s = r'(?si)^[ \t]*{}\s+[\w\s,]*\b{}\b'.format(ws[0],ws[1])
            r = self.view.find(s,0, sublime.IGNORECASE)
            if r:
                sublime_util.move_cursor(self.view,r.a)
        else :
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
        v.set_syntax_file('Packages/Smart VHDL/Find Results VHDL.hidden-tmLanguage')
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
                    if lvl<32 :
                        txt += self.printSubmodule(x[1],lvl+1)
                    else :
                        print('[VHDL.navigation] Hierarchy with more than 20 level not supported !')
                        return
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

###########################################################
# Find all instances of current module or selected module #
class VhdlFindInstanceCommand(sublime_plugin.TextCommand):

    def run(self,edit):
        mname = getModuleName(self.view)
        sublime.status_message("Find Instance can take some time, please wait ...")
        sublime.set_timeout_async(lambda x=mname: self.findInstance(x))

    def findInstance(self, mname):
        projname = sublime.active_window().project_file_name()
        if projname not in vhdl_module.list_module_files:
            vhdl_module.VhdlModuleInstCommand.get_list_file(None,projname,None)
        inst_dict = {}
        cnt = 0
        re_str = r'(?si)^\s*(\w+)\s*:\s*(?:use\s+)?(?:entity\s+)?(\w+\.)?{}(\s*\(\s*\w+\s*\))?\s+(port|generic)'.format(mname)
        p = re.compile(re_str,re.MULTILINE)
        for fn in vhdl_module.list_module_files[projname]:
            with open(fn) as f:
                txt = f.read()
                if mname in txt:
                    for m in re.finditer(p,txt):
                        cnt+=1
                        lineno = txt.count("\n",0,m.start()+1)+1
                        res = (m.groups()[0].strip(),lineno)
                        if fn not in inst_dict:
                            inst_dict[fn] = [res]
                        else:
                            inst_dict[fn].append(res)
        if inst_dict:
            v = sublime.active_window().new_file()
            v.set_name(mname + ' Instances')
            v.set_syntax_file('Packages/Smart VHDL/Find Results VHDL.hidden-tmLanguage')
            v.settings().set("result_file_regex", r"^(.+):$")
            v.settings().set("result_line_regex", r"\(line: (\d+)\)$")
            v.set_scratch(True)
            txt = mname + ': %0d instances.\n\n' %(cnt)
            for (name,il) in inst_dict.items():
                txt += name + ':\n'
                for i in il:
                    txt += '    - {0} (line: {1})\n'.format(i[0].strip(),i[1])
                txt += '\n'
            v.run_command('insert_snippet',{'contents':str(txt)})
        else :
            sublime.status_message("[VHDL] No instance found !")

######################################################################################
# Create a new buffer showing the class hierarchy (sub-class instances) of current class #
navBar = {}

PHANTOM_TEMPLATE = """
<body id="sv-navbar">
<style>
    html, body {{
        margin: 0;
        padding: 0;
        background-color: transparent;
    }}
    a {{
        text-decoration: none;
        color: {1};
    }}
    .content {{color: {1};}}
</style>
<span class="content">{0}</span>
</body>
"""


def getObjName(view):
    r = view.sel()[0]
    nameList = []
    rList = view.find_all(r'(?si)^[ \t]*(entity)\s+(\w+)',0,r'\1 \2',nameList)
    rList += view.find_all(r'(?si)^[ \t]*(architecture)\s+(?:\w+)\s+of\s+(\w+)',0,r'\1 \2',nameList)
    rList += view.find_all(r'(?si)^[ \t]*(package)(?:\s+body\b)?\s+(\w+)',0,r'\1 \2',nameList)
    t = ''
    name = ''
    if rList:
        t,_,name = nameList[0].partition(' ')
        # Handle case where there is multiple class in a file
        # and select the one closest to the cursor
        for (rf,n) in zip(rList,nameList):
            if rf.a < r.a:
                t,_,name = n.partition(' ')
            else:
                break
    return t,name

class VhdlShowNavbarCommand(sublime_plugin.TextCommand):

    def run(self,edit):
        t,name = getObjName(self.view)
        if not name:
            return
        txt = self.view.substr(sublime.Region(0, self.view.size()))

        info = {
            'type': t, 'name': name, 'port': {},
            'signal': {}, 'alias': {}, 'const': {},
            'inst': [], 'proc':{}, 'func':{}};
        x = vhdl_util.get_ports(txt,name);
        if x and 'port' in x:
            info['port'] = x['port']
        info['inst'] = vhdl_util.get_inst_list(txt,name);
        x = vhdl_util.get_signals(txt,name);
        if x :
            for t in ['signal', 'const', 'alias'] :
                if t in x:
                    info[t] = x[t]
        txt = vhdl_util.clean_comment(txt)
        info['func'] = vhdl_util.get_function_list(txt, name, True);
        info['proc'] = vhdl_util.get_procedure_list(txt, name, True);
        info['process'] = vhdl_util.get_process_list(txt, name, True);

        sublime.set_timeout_async(lambda info=info, w=self.view.window(): self.showHierarchy(info,w))

    def showHierarchy(self,mi,w):
        # Save info in global for later access
        info = {'dict':{}, 'view':None,'fname':''}
        info['view'] = self.view
        info['fname'] = self.view.file_name()

        global navBar
        w = sublime.active_window()
        wid = w.id()
        navbar_flag = w.settings().get('navbar-hdl-shared', 0)
        if wid not in navBar:
            l = w.get_layout()
            nb_col = len(l['cols'])
            if navbar_flag != 0:
                if nb_col < 2:
                    navbar_flag = 0
                else :
                    gid = len(l['cells'])-1
                    vl = w.views_in_group(gid)
                    if len(vl) == 1:
                        if not vl[0].name().endswith(' Hierarchy') :
                            navbar_flag = 0
                    else :
                        navbar_flag = 0
            if navbar_flag == 0:
                l['cols'].append(1.0)
                width = self.view.settings().get('vhdl.navbar_width',0.2)
                delta = width / (nb_col-1)
                for i in range(1,nb_col) :
                    l['cols'][i] -= i * delta
                l['cells'].append([nb_col-1,0,nb_col,1])
                w.set_layout(l)
                w.focus_group(len(l['cells'])-1)
                navBarView = w.new_file()
                navBarView.settings().set("tab_size", 2)
            else :
                l = w.get_layout()
                group_id = len(l['cells'])-1
                w.focus_group(group_id)
                navBarView = w.active_view_in_group(group_id)
                navBarView.run_command("select_all")
                navBarView.run_command("right_delete")
            navBarView.set_scratch(True)
            navBar[wid] = {'view':navBarView, 'settings':{}, 'sv_on': False}
            navBar[wid]['settings']['update'] = 1
            navBar[wid]['settings']['show_port'] = self.view.settings().get('vhdl.navbar_show_port',True)
            navBar[wid]['settings']['show_signal'] = self.view.settings().get('vhdl.navbar_show_signal',False)
            navBar[wid]['settings']['show_process'] = self.view.settings().get('vhdl.navbar_show_process',False)
            navBar[wid]['settings']['show_alias'] = self.view.settings().get('vhdl.navbar_show_alias',False)
            navBar[wid]['settings']['show_const'] = self.view.settings().get('vhdl.navbar_show_const',False)
            navBar[wid]['settings']['font_size'] = self.view.settings().get('vhdl.navbar_font_size',10)
        else :
            navBar[wid]['view'].run_command("select_all")
            navBar[wid]['view'].run_command("right_delete")

        if 'vhdl' not in navBar[wid]['view'].scope_name(0):
            navBar[wid]['view'].set_syntax_file('Packages/Smart VHDL/navbar.sublime-syntax')
        w.settings().set('navbar-hdl-shared', navbar_flag | 2)

        navBar[wid]['info'] = info
        navBar[wid]['childless'] = []

        # Create content
        top_level = mi['name']
        txt = '{}\n'.format(top_level)
        txt += '-'*len(top_level) + '\n'
        txt += self.printContent(1,mi,navBar[wid])

        navBar[wid]['view'].set_name(top_level + ' Hierarchy')
        navBar[wid]['view'].run_command('insert_snippet',{'contents': '$x', 'x':txt})

        # Add phantoms
        self.build_phantoms(wid)

        # Fold functions arguments
        navBar[wid]['view'].run_command("fold_by_level", {"level": 2})
        # Ensure focus is at beginning of file
        sublime_util.move_cursor(navBar[wid]['view'],0)

    def printContent(self,lvl,ti, nb):
        txt = ''
        # print(ti)
        if 'port' in ti and ti['port'] and (nb['settings']['show_port'] and lvl==1):
            txt += '{}Ports:\n'.format('  '*(lvl-1))
            name_len = max([len(x['name']) for x in ti['port']])
            for p in ti['port'] :
                d = self.get_dir_symb(p)
                txt += '{indent}* {dir} {name:<{l}} : {type}\n'.format(indent='  '*lvl,dir=d,name=p['name'],type=p['type'],l=name_len)
        if 'const' in ti and ti['const'] and (nb['settings']['show_const'] and lvl==1):
            txt += 'Constants:\n'
            name_len = max([len(x['name']) for x in ti['const']])
            for p in ti['const'] :
                txt += '{indent}* {name:<{l}} : {type} := {value}\n'.format(indent='  '*lvl,name=p['name'],type=p['type'],value=p['value'],l=name_len)
        if 'signal' in ti and ti['signal'] and (nb['settings']['show_signal'] and lvl==1):
            txt += 'Signals:\n'
            name_len = max([len(x['name']) for x in ti['signal']])
            for p in ti['signal'] :
                txt += '{indent}* {name:<{l}} : {type}\n'.format(indent='  '*lvl,name=p['name'],type=p['type'],l=name_len)
        if 'alias' in ti and ti['alias'] and (nb['settings']['show_alias'] and lvl==1):
            txt += 'Alias:\n'
            name_len = max([len(x['name']) for x in ti['alias']])
            for p in ti['alias'] :
                if 'type' in p and p['type']!='alias':
                    txt += '{indent}* {name:<{l}} : {type} := {value}\n'.format(indent='  '*lvl,name=p['name'],type=p['type'],value=p['value'],l=name_len)
                else :
                    txt += '{indent}* {name:<{l}} : {value}\n'.format(indent='  '*lvl,name=p['name'],value=p['value'],l=name_len)
        if 'inst' in ti and ti['inst']:
            if lvl==1 and (nb['settings']['show_port'] or nb['settings']['show_signal']):
                txt += '{}Instances:\n'.format('  '*(lvl-1))
            else :
                lvl -= 1
            for inst in ti['inst']:
                if inst[1] in nb['childless']:
                    symb = u'\u180E'
                else :
                    symb = ''
                txt += '{}{}{name} ({type})\n'.format('  '*lvl,symb,name=inst[0],type=inst[1])
        if 'proc' in ti and ti['proc'] :
            txt += '{}Procedures:\n'.format( '  '*(lvl-1))
            for n,v in ti['proc'].items():
                txt += '  '*lvl
                txt += '{name}\n'.format(name=n)
                if v['args'] :
                    name_len = max([len(x['name']) for x in v['args']])
                    for p in v['args'] :
                        d = self.get_dir_symb(p)
                        txt += '{indent}* {dir} {name:<{l}} : {type}\n'.format(indent='  '*(lvl+1),dir=d,name=p['name'],type=p['type'],l=name_len)
        if 'func' in ti and ti['func'] :
            txt += '{}Functions:\n'.format( '  '*(lvl-1))
            for n,v in ti['func'].items():
                txt += '  '*lvl
                txt += '{name}\n'.format(name=n)
                if v['args'] :
                    name_len = max([len(x['name']) for x in v['args']])
                    for p in v['args'] :
                        d = self.get_dir_symb(p)
                        txt += '{indent}* {dir} {name:<{l}} : {type}\n'.format(indent='  '*(lvl+1),dir=d,name=p['name'],type=p['type'],l=name_len)
        if 'process' in ti and ti['process'] and nb['settings']['show_process']:
            txt += '{}Process:\n'.format( '  '*(lvl-1))
            for n in ti['process']:
                txt += '  '*lvl
                txt += '* {name}\n'.format(name=n)
        return txt

    def get_dir_symb(self, ti):
        if 'tag' in ti and ti['tag'] and ti['tag'].lower()=='constant' :
            d = ' =>'
        elif 'dir' not in ti or not ti['dir']:
            d = ' ->'
        else :
            dir_lc = ti['dir'].lower()
            if dir_lc=='in':
                d = ' ->'
            elif dir_lc=='out':
                d = '<- '
            elif dir_lc=='inout':
                d = '<->'
        return d

    def build_phantoms(self,wid):
        view = navBar[wid]['view']
        # Clear exiting phantoms if nay
        if 'phantomSet' in navBar[wid] :
            navBar[wid]['view'].erase_phantoms('sv-navbar')
        phantoms = []
        pid = 0
        regions = view.find_by_selector('storage.name.type.userdefined.hierarchy-vhdl')
        for r in regions :
            name = view.substr(r)
            ilc = view.indentation_level(r.a)
            pnl = view.line(r).b+1
            iln = view.indentation_level(pnl)
            # print('[Phantoms] Name {} - Point {} ({}) : indent = {} vs {}, folded = {}'.format(name,pnl,view.rowcol(pnl),iln,ilc,view.is_folded(sublime.Region(pnl))))
            # print('indent level for member {} = {} {}'.format(name,ilc,iln))
            if name in navBar[wid]['childless'] :
                content = '<a>-</a>'
            elif ilc>=iln :
                content = '<a href="type:{}:{}:{}:{}">+</a>'.format(name,r.a,ilc,pid)
            elif view.is_folded(sublime.Region(pnl)) :
                content = '<a href="unfold:{}:{}">+</a>'.format(r.a,pid)
            else :
                content = '<a href="fold:{}:{}">-</a>'.format(r.a,pid)
            r = sublime.Region(view.line(r).a + ilc*2)
            phantoms.append(sublime.Phantom(
                region = r,
                content=PHANTOM_TEMPLATE.format(content,colors['operator']),
                layout=sublime.LAYOUT_INLINE,
                on_navigate=self.on_navigate)
            )
            pid += 1
        regions = view.find_by_selector('meta.annotation.marker')
        for r in regions :
            phantoms.append(sublime.Phantom(
                region = r,
                content=PHANTOM_TEMPLATE.format('-',colors['operator']),
                layout=sublime.LAYOUT_INLINE)
            )
        if len(phantoms)>0:
            navBar[wid]['phantomSet'] = sublime.PhantomSet(navBar[wid]['view'], "sv-navbar")
            navBar[wid]['phantom'] = phantoms
            navBar[wid]['phantomSet'].update(phantoms)

    def change_phantom(self,wid,v,pid,content):
        v.erase_phantoms('sv-navbar')
        navBar[wid]['phantomSet'] = sublime.PhantomSet(v, "sv-navbar")
        navBar[wid]['phantom'][pid].content = PHANTOM_TEMPLATE.format(content,colors['operator'])
        navBar[wid]['phantomSet'].update(navBar[wid]['phantom'])

    def on_navigate(self,href):
        global navBar
        href_s = href.split(':')
        w = sublime.active_window()
        wid = w.id()
        view = navBar[wid]['info']['view']
        v =  navBar[wid]['view']
        # print('[VHDL.Navbar] on_navigate = {}'.format(href_s))
        if href_s[0]=="type" :
            if href_s[1] in navBar[wid]['childless'] :
                self.change_phantom(wid,v,int(href_s[4]),'<a>-</a>')
                return
            ti = vhdl_module.lookup_type(view,href_s[1],2)
            # print(ti)
            if not ti or 'type' not in ti:
                navBar[wid]['childless'].append(href_s[1])
                self.change_phantom(wid,v,int(href_s[4]),'<a>-</a>')
                # print('Type {} not found: {}'.format(href_s[1],ti))
                return
            if ti['type'].lower() == 'architecture' :
                if 'fname' in ti :
                    mi = {}
                    mi['inst'] = vhdl_util.get_inst_list_from_file(ti['fname'][0])
                    txt = self.printContent(2,mi,navBar[wid])
                    if txt:
                        r = self.insert_text_next_line(v,int(href_s[2]),txt)
                        self.build_phantoms(wid)
                    else :
                        navBar[wid]['childless'].append(ti['name'])
                        self.change_phantom(wid,v,int(href_s[4]),'<a>-</a>')
            else :
                # print('Unsupported Type {} not found: {}'.format(href_s[1],ti))
                return
        elif href_s[0]=="fold" :
            r_start = int(href_s[1])
            s = sublime.Region(v.line(r_start).b+1)
            s = v.indented_region(s.b)
            if not s.empty():
                s.a -= 1
                s.b -= 1
                v.fold(s)
            pid = int(href_s[2])
            t = '<a href="unfold:{}:{}">+</a>'.format(r_start,pid)
            self.change_phantom(wid,v,pid,t)
        elif href_s[0]=="unfold" :
            r_start = int(href_s[1])
            s = sublime.Region(v.line(r_start).b+1)
            v.unfold(s)
            pid = int(href_s[2])
            t = '<a href="fold:{}:{}">-</a>'.format(r_start,pid)
            self.change_phantom(wid,v,pid,t)
            self.fold_methods(v,s)

    def insert_text_next_line(self, v, r, txt):
        r = v.line(sublime.Region(r))
        v.sel().clear()
        v.sel().add(r.b)
        # Workaround weird auto-indentation behavior of insert_snippet
        v.run_command('insert_snippet', {'contents': '\n'})
        v.run_command('insert_snippet', {'contents': '$x', 'x':txt[:-1]})
        return r

    def fold_methods(self, v, r_start) :
        folds = []
        rs = v.indented_region(r_start.b)
        r = v.find("Methods:",r_start.b)
        ilm = v.indentation_level(r.a)+1
        if r.a >= rs.b:
            return
        while(True) :
            # Go next line
            r = sublime.Region(v.line(r).b+1)
            il = v.indentation_level(r.a)
            if il < ilm or r.b >= rs.b:
                break
            else :
                s = sublime.Region(v.line(r).b+1)
                il = v.indentation_level(s.a)
                if il < ilm or r.b >= rs.b:
                    break
                elif il > ilm :
                    s = v.indented_region(s.b)
                    if not s.empty():
                        r = s
                        s.a -= 1
                        s.b -= 1
                        folds.append(s)
        v.fold(folds)

# Toggle Open/close navigation Bar
class VhdlToggleNavbarCommand(sublime_plugin.WindowCommand):

    def run(self, cmd='toggle'):
        global navBar
        wid = self.window.id()
        av = self.window.active_view()
        # print('[VHDL] : wid = {}, navbar={}, cmd={}'.format(wid,navBar.keys(),cmd))
        if wid in navBar and cmd != 'open':
            nv = navBar[wid]['view']
            if av is None or av == nv :
                av = navBar[wid]['info']['view']
            self.window.settings().set('navbar-hdl-shared', 0)
            # Close the navBar view
            if wid not in navBar :
                return
            del navBar[wid]
            sublime.active_window().run_command("verilog_toggle_navbar",{'cmd':'disable'})
            if cmd == 'disable' :
                return
            if cmd == 'toggle' :
                # print('[VHDL] Focus on view {}'.format(nv.id()))
                self.window.focus_view(nv)
                nv.set_scratch(True)
                self.window.run_command("close_file")

            # Remove the extra group in which the navbar was created
            l = self.window.get_layout()
            width = l['cols'][-1] - l['cols'][-2]
            l['cols'].pop()
            nb_col = len(l['cols'])
            if nb_col == 1:
                return
            delta = width / (nb_col-1)
            for i in range(1,nb_col) :
                l['cols'][i] += i*delta
            l['cells'].pop()
            self.window.set_layout(l)
            # Focus back on initial view
            # print('Focux back on orginal view!')
            # print('[VHDL] Focus back on active view {}'.format(av.id()))
            self.window.focus_view(av)
        elif self.window.settings().get('navbar-hdl-shared', 0) != 0 and cmd != 'open':
            self.window.settings().set('navbar-hdl-shared', 0)
            sublime.active_window().run_command("verilog_toggle_navbar",{'cmd':'close'})
        elif cmd in ['open','toggle'] and av :
            # print('[VHDL] Running show navbar')
            if 'systemverilog' in  av.scope_name(0):
                av.run_command("verilog_show_navbar")
            else :
                av.run_command("vhdl_show_navbar")

# Update the navigation bar
class VhdlUpdateNavbarCommand(sublime_plugin.EventListener):

    def on_activated_async(self,view):
        w = sublime.active_window()
        wid = w.id()
        if wid not in navBar:
            return;
        scope =  view.scope_name(0)
        # print('[VHDL] : fnamer={} - {} ({}), update={}, scope={}, navbar_flag={}'.format(navBar[wid]['info']['fname'],view.file_name(),view.id(),navBar[wid]['settings']['update'],scope,w.settings().get('navbar-hdl-shared', 0)))
        if navBar[wid]['info']['fname'] == view.file_name():
            if 'vhdl' in navBar[wid]['view'].scope_name(0):
                return
            elif 'source.vhdl' in scope:
                view.run_command("vhdl_show_navbar")
        if navBar[wid]['settings']['update'] == 0:
            return
        if 'source.vhdl' in scope:
            view.run_command("vhdl_show_navbar")
        elif 'source.systemverilog' in scope:
            navbar_flag = w.settings().get('navbar-hdl-shared', 0)
            if navbar_flag & 1 == 0 :
                view.run_command("verilog_show_navbar")

        # Changes fontsize of navbar content.
        if 'text.hierarchy' in scope:
            fontSize = navBar[wid]['settings']['font_size']
            if fontSize > 0:
                view.settings().set("font_size", fontSize)

# Update the navigation bar
class VhdlToggleLockNavbarCommand(sublime_plugin.WindowCommand):

    def run(self):
        global navBar
        wid = self.window.id()
        if wid in navBar :
            if navBar[wid]['settings']['update'] == 0:
                navBar[wid]['settings']['update'] = navBar[wid]['view'].settings().get('vhdl.navbar_update',15)
                # If default is 0 unlock fully
                if navBar[wid]['settings']['update'] == 0:
                    navBar[wid]['settings']['update'] = 15
                self.window.status_message('VHDL NavBar unlocked ({})'.format(navBar[wid]['settings']['update']))
            else :
                navBar[wid]['settings']['update'] = 0
                self.window.status_message('VHDL NavBar locked ')


class VhdlHandleNavbarCommand(sublime_plugin.ViewEventListener):

    @classmethod
    def is_applicable(cls, settings):
        return settings.get('syntax') == 'Packages/Smart VHDL/navbar.sublime-syntax'

    def on_close(self):
        sublime.active_window().run_command("vhdl_toggle_navbar",{'cmd':'close'})
        sublime.active_window().run_command("verilog_toggle_navbar",{'cmd':'close'})

    def on_text_command(self, command_name, args):
        # Detect double click
        double_click = command_name == 'drag_select' and 'by' in args and args['by'] == 'words'
        if not double_click:
            return
        s = self.view.sel()[0]
        scope = self.view.scope_name(s.a)
        region = self.view.word(s)
        name = self.view.substr(region)
        if name.startswith(u'\u180E'):
            name = name[1:]
        w = sublime.active_window()
        wid = w.id()
        v = navBar[wid]['info']['view']
        debug = v.settings().get("vhdl.debug", False)
        if debug: print('[NavBar: DoubleClick] s = {}, r={} scope="{}"'.format(s,region,scope))
        if 'userdefined' in scope:
            ti = vhdl_module.lookup_type(self.view,name,2)
            if ti and 'fname' in ti and ti['fname'] :
                fname = '{}:{}:{}'.format(ti['fname'][0],ti['fname'][1],ti['fname'][2])
                w.focus_view(v)
                w.open_file(fname,sublime.ENCODED_POSITION)
        elif 'entity.name.method' in scope:
            cname = navbar_get_class(self.view,s)
            if cname :
                filelist = w.lookup_symbol_in_index(cname)
                if debug: print('[NavBar: DoubleClick] Class {} -> filelist = {}'.format(cname, filelist))
                if filelist :
                    sublime_util.goto_symbol_in_file(v,name,sublime_util.normalize_fname(filelist[0][0]))
            else :
                # sublime_util.goto_symbol_in_file(v,name,v.file_name())
                # sublime.set_timeout(lambda w=w, name=name, debug=debug: move_to_def(w.active_view(),name,debug))
                if debug: print('[NavBar: DoubleClick] MoveToDef of {}'.format(name))
                move_to_def(v,name,debug)
        else:
            cname = navbar_get_class(self.view,s)
            if cname :
                # print('[VHDL.Navbar] Class for {} is {}'.format(name,cname))
                if cname in ['function','task']:
                    return
                v,fname = sublime_util.goto_index_symbol(v,cname)
                if v:
                    # print('GotoIndexSymbols -> {} ({})'.format(fname,v.id()))
                    if fname:
                        global callbacks_on_load
                        callbacks_on_load[fname] = lambda v=v, name=name: goto_first_occurence(v,name)
                        return
                    else :
                        goto_first_occurence(v,name)
            else :
                # print('[VHDL.Navbar] Navigate to first occurence of {}'.format(name))
                goto_first_occurence(v,name)

def navbar_get_class(view,r):
    il = view.indentation_level(r.a)
    # Not local member : find to which class this belongs
    if il > 1 :
        r = view.indented_region(r.a)
        p = view.find_by_class(r.a,False,sublime.CLASS_WORD_START)
        # If going up one level gives a keyword, it means we need to go up another level
        scope = view.scope_name(p)
        if 'keyword' in scope:
            r = view.indented_region(p)
            p = view.find_by_class(r.a,False,sublime.CLASS_WORD_START)
        cname = view.substr(view.word(p))
    else :
        cname = ''
    return cname


def goto_first_occurence(view,name):
    r = sublime.Region(0)
    max_rb = view.size()
    while r.b < max_rb :
        r = view.find(r'\b{}\b'.format(name),r.b)
        # print('Found "{}" at {} (max={})'.format(name,r,max_rb))
        if not r:
            return
        if 'comment' not in view.scope_name(r.a):
            break;
    view.window().focus_view(view)
    sublime_util.move_cursor(view,r.a)


def move_to_def(view,name,debug=False):
    sublime.active_window().focus_view(view)
    r = view.find(r'\b{}\b'.format(name),0)
    max_rb = view.size()
    if debug: print('[move_to_def] Region = {} (nbSel = {}) / Max = {}'.format(r,len(view.sel()),max_rb))
    tmp = -1
    while r.b < max_rb :
        s = view.scope_name(r.a)
        if debug: print('[move_to_def] Scope = {} @ {}'.format(s,r))
        if 'definition' in s:
            sublime_util.move_cursor(view,r.a)
            return
        else :
            if tmp==-1 and 'prototype' in s:
                tmp = r.a
            prev = r.a
            r = view.find(r'\b{}\b'.format(name),r.b,sublime.IGNORECASE)
            if r is None or r.a == prev or r.a < 0 :
                if debug: print('[move_to_def] Aborting search, new region = {} '.format(s,r))
                if tmp != -1:
                    sublime_util.move_cursor(view,tmp)
                return
    if debug: print('Def not found for {}'.format(name))

