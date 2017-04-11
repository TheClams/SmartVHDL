import sublime, sublime_plugin
import re, string, os, sys, functools, mmap, pprint, imp, threading
from collections import Counter
from plistlib import readPlistFromBytes

try:
    from SmartVHDL.util import vhdl_util
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), "util"))
    import vhdl_util

############################################################################
# Init
tooltip_css = ''
tooltip_flag = 0

def plugin_loaded():
    imp.reload(vhdl_util)
    # Ensure the preference settings are properly reloaded when changed
    global pref_settings
    pref_settings = sublime.load_settings('Preferences.sublime-settings')
    pref_settings.clear_on_change('reload')
    pref_settings.add_on_change('reload',plugin_loaded)
    # Ensure the VHDL settings are properly reloaded when changed
    global vhdl_settings
    vhdl_settings = sublime.load_settings('SystemVerilog.sublime-settings')
    vhdl_settings.clear_on_change('reload')
    vhdl_settings.add_on_change('reload',plugin_loaded)
    global tooltip_flag
    if vhdl_settings.get('vhdl.tooltip_hide_on_move',True):
        tooltip_flag = sublime.HIDE_ON_MOUSE_MOVE_AWAY
    else:
        tooltip_flag = 0
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
# Display type of the signal/variable under the cursor into the status bar #

# Event onHover to display the popup
class VerilogShowTypeHover(sublime_plugin.EventListener):
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
        # lookup for a signal/variable declaration in current file
        lines = self.view.substr(sublime.Region(0, self.view.line(region).b))
        ti = vhdl_util.get_type_info(lines,var_name)
        if ti:
            txt = ti['decl']
        return txt,ti

    def color_str(self,s, addLink=False, ti_var=None):
        # Split all text in word, special character, space and line return
        words = re.findall(r"\w+|[^\w\s]|\s+", s)
        print('String = "{}" \n Split => {}'.format(s,words))
        sh = ''
        idx_type = -1
        if words[0] in ['signal','variable','constant']:
            idx_type = 6
        elif words[0] in ['port']:
            idx_type = 8
        for i,w in enumerate(words):
            # Check for keyword
            if w in ['signal','port','constant','array','downto','upto','of','in','out','inout']:
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

