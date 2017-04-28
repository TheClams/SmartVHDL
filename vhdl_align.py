import sublime, sublime_plugin
import re, string, os, imp

try:
    from SmartVHDL.util import sublime_util
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), "util"))
    import sublime_util

def plugin_loaded():
    imp.reload(sublime_util)

############################################################################

class VhdlAlign(sublime_plugin.TextCommand):

    def run(self,edit, cmd=""):
        if len(self.view.sel())==0 : return
        # Save information of selected text
        region = self.view.sel()[0]
        row,col = self.view.rowcol(region.a)
        # Extract scope and make sure we have same at beginning and end of the region
        scope = self.view.scope_name(region.a)
        if region.b > region.a :
            if self.view.scope_name(region.b) != scope :
                scope = ''
        txt = ''
        # Component/Entity instantiation
        if '_instantiation' in scope:
            if 'meta.block.entity_instantiation' in scope:
                region = sublime_util.expand_to_scope(self.view,'meta.block.entity_instantiation',region)
            else :
                region = sublime_util.expand_to_scope(self.view,'meta.block.component_instantiation',region)
            # Make sure to get complete line to be able to get initial indentation
            region = self.view.line(region)
            txt  = self.view.substr(region)
            ilvl = self.view.indentation_level(region.a)
            txt  = self.alignInstance(txt,ilvl)
        #
        if txt:
            self.view.replace(edit,region,txt)
            sublime_util.move_cursor(self.view,self.view.text_point(row,col))
        else :
            sublime.status_message('No alignement support for this block of code.')

    def alignInstance(self,txt,ilvl):
        m = re.match(r'(?si)(?P<emptyline>\n*)[ \t]*(?P<inst_name>\w+)\s*:\s*(?P<type>(?:entity\s+work\.)?\w+\b(?:\([\w\s]+\))?)\s*(?:(?P<gen_or_port>generic|port)\s+map)\s*\((?P<content>.*)\)\s*;',txt)
        if not m:
            return ''
        txt_new = m.group('emptyline') + '\t'*(ilvl)
        txt_new += '{} : {}\n'.format(m.group('inst_name').strip(),m.group('type').strip())
        port_content = m.group('content')
        # Extract generic map part if it exist and provide alignment
        if m.group('gen_or_port')=='generic' :
            m_content = re.match(r'(?si)(?P<gen_content>.*)\bport\s+map\s*\((?P<port_content>.*)',port_content)
            if not m_content:
                return ''
            gen_content = m_content.group('gen_content')
            # create a temporary string with no comment and find last closing parenthesis
            s_tmp = re.sub(r'--.*$',lambda m : ' '*len(m.group()) ,gen_content, flags=re.MULTILINE)
            pos_end = s_tmp[::-1].index(')')
            sep_content = gen_content[len(gen_content)-pos_end:].strip()
            gen_content = gen_content[:-pos_end-1].strip()
            txt_new += '\t'*(ilvl+1) + 'generic map (\n'
            txt_new += self.alignInstanceBinding(gen_content,ilvl+2)
            txt_new += '\t'*(ilvl+1) + ')\n'
            if sep_content:
                txt_new += '\t'*(ilvl+1) + sep_content + '\n'
            port_content = m_content.group('port_content')
        # Align port map
        txt_new += '\t'*(ilvl+1) + 'port map (\n'
        txt_new += self.alignInstanceBinding(port_content,ilvl+2)
        txt_new += '\t'*(ilvl+1) + ');\n'
        return txt_new

    def alignInstanceBinding(self,txt,ilvl):
        # ensure one bind per line
        txt = re.sub(r',[ \t]*(\w+)',r',\n\1',txt.strip())
        re_bind = r'^\s*(?P<port>\w+(?:\s*\(./?\))?)\s*=>(?P<bind>.*?)(?P<sep>,?)(?P<comment>[ \t]*--.*)?$'
        bind = re.findall(re_bind,txt,flags=re.MULTILINE)
        port_len = max([len(x[0].strip()) for x in bind])
        bind_len = max([len(x[1].strip()) for x in bind])
        # print('[alignInstanceBinding] : Max length port = {} , bind = {}'.format(max(port_len),max(bind_len)))
        txt_new = ''
        for l in txt.splitlines() :
            # check if match binding
            m = re.match(re_bind,l)
            # Add indent level
            txt_new += '\t'*ilvl
            # in case of binding align port and signal together
            if m :
                txt_new += m.group('port').strip().ljust(port_len)
                txt_new += ' => '
                txt_new += m.group('bind').strip().ljust(bind_len)
                if m.group('sep'):
                    txt_new += ','
                else:
                    txt_new += ' '
                if m.group('comment'):
                    txt_new += ' ' + m.group('comment').strip()
            # No Binding ? copy line with indent level
            else :
                txt_new += l.strip()
            txt_new += '\n'
        return txt_new

