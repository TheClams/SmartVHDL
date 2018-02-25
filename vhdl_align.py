import sublime, sublime_plugin
import re, string, os, imp, sys

try:
    from .util import vhdl_util
    from .util import sublime_util
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), "util"))
    import sublime_util
    import vhdl_util

def plugin_loaded():
    imp.reload(sublime_util)
    imp.reload(vhdl_util)

############################################################################

class VhdlAlign(sublime_plugin.TextCommand):

    s_id_list = r'\w+(?:\s*,[\s\w,]+)?'
    s_comment = r'^(?P<space>[\ \t]*)--[\ \t]*(?P<comment>.*?)(\n|$)'

    def run(self,edit, cmd=""):
        if len(self.view.sel())==0 : return
        tab_size = int(self.view.settings().get('tab_size', 4))
        use_space = self.view.settings().get('translate_tabs_to_spaces')
        self.indent_space = ' '*tab_size
        self.cfg = {'tab_size': tab_size, 'use_space':use_space}
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
            ilvl = self.getIndentLevel(self.view.substr(region))
            txt  = self.alignInstance(txt,ilvl)
        elif 'meta.block.entity.vhdl' in scope:
            region = sublime_util.expand_to_scope(self.view,'meta.block.entity',region)
            # Make sure to get complete line to be able to get initial indentation
            region = self.view.line(region)
            txt  = self.view.substr(region)
            ilvl = self.getIndentLevel(self.view.substr(region))
            txt  = self.alignEntity (txt,ilvl)
        #
        if txt:
            self.view.replace(edit,region,txt)
            sublime_util.move_cursor(self.view,self.view.text_point(row,col))
        else :
            sublime.status_message('No alignement support for this block of code.')


    def getIndentLevel(self,txt):
        line = txt[:txt.find('\n')]
        # Make sure there is no mix tab/space
        if self.cfg['use_space']:
            line = line.replace('\t',self.indent_space)
        else:
            line = line.replace(self.indent_space,'\t')
        cnt = len(line) - len(line.lstrip())
        if self.cfg['use_space']:
            cnt = int(cnt/self.cfg['tab_size'])
        return cnt

    def alignEntity(self,txt,ilvl):
        # TODO: Extract comment location to be sure to handle all case of strange comment location
        m = re.search(r"""(?six)
            (?P<type>entity|component)\s+(?P<name>\w+)\s+is\s+
            (generic\s*\((?P<generic>.*?)\)\s*;\s*)?
            (port\s*\((?P<port>.*?)\)\s*;)\s*
            (?P<ending>end\b(\s+entity)?(\s+(?P=name))?)\s*;
            """, txt, re.MULTILINE)
        if m is None:
            return txt

        txt_new = '\t'*(ilvl)
        txt_new += '{} {} is \n'.format(m.group('type'),m.group('name'))

        if m.group('generic') :
            # Extract all params info to know width of each for future alignement
            params = vhdl_util.clean_comment(m.group('generic'))
            re_params = r'''(?six)^[\ \t]*
                (?P<name>\w+)[\ \t]*:[\ \t]*
                (?P<type>\w+)\b[\ \t]*
                (?P<range>\([^\)]*\)|range[\ \t]+[\w\-\+]+[\ \t]+(?:(?:down)?to)[\ \t]+[\w\-\+]+)?
                (?:[\ \t]*:=[\ \t]*(?P<init>.*?))
                [\ \t]*(?P<end>;)?[\ \t]*(?:--[\ \t]*(?P<comment>[^\n]*))?$'''
            decl = re.findall(re_params, params ,flags=re.MULTILINE)
            name_len_l  = [] if not decl else [len(x[0].strip()) for x in decl]
            type_len_l  = [] if not decl else [len(x[1].strip()) for x in decl]
            range_len_l = [] if not decl else [len(x[2].strip()) for x in decl]
            init_len_l  = [] if not decl else [len(x[3].strip()) for x in decl]
            name_len  = 0 if not name_len_l  else max(name_len_l )
            type_len  = 0 if not type_len_l  else max(type_len_l )
            range_len = 0 if not range_len_l else max(range_len_l)
            init_len  = 0 if not init_len_l  else max(init_len_l )+4
            all_range = [x[2] for x in decl if 'range' in x[2]]
            has_range = len(all_range)>0
            if has_range:
                range_len +=1

            #print(decl)
            #print('Length params: N={} T={} R={} I={}'.format(name_len,type_len,range_len,init_len))
            comment_pos = name_len + 1 + type_len + range_len + init_len

            # Add params with alignement and copy non params line as is
            txt_new += '{}generic (\n'.format('\t'*(ilvl+1))
            for l in m.group('generic').strip().splitlines() :
                mp = re.match(re_params,l)
                if mp :
                    txt_new += '{ident}{name:<{length}} : '.format(ident='\t'*(ilvl+2),name=mp.group('name'),length=name_len)
                    txt_new += '{type:<{length}}'.format(type=mp.group('type'),length=type_len)
                    if range_len>0 :
                        if mp.group('range') :
                            if 'range' in mp.group('range'):
                                txt_new += ' '
                            txt_new += '{range:<{length}}'.format(range=mp.group('range'),length=range_len-1)
                        else :
                            txt_new += ' '*(range_len)
                    if init_len>0 :
                        if mp.group('init') :
                            txt_new += ' := {init:<{length}}'.format(init=mp.group('init'),length=init_len-4)
                        else :
                            txt_new += ' '*(init_len)
                    txt_new += ';' if mp.group('end') else ' '
                    if mp.group('comment'):
                        txt_new += ' -- {}'.format(mp.group('comment').strip())
                else :
                    mc = re.match(self.s_comment,l)
                    if mc :
                        pos = comment_pos if self.getIndentLevel(mc.group('space')) > (ilvl+2) else ilvl+2
                        txt_new += '{}{}'.format('\t'*comment_pos,mc.group(0).strip())
                    else :
                        # print('No match for "{}"'.format(l))
                        txt_new += l
                txt_new += '\n'
            txt_new += '{});\n'.format('\t'*(ilvl+1))

        if m.group('port') :
            # Extract all ports info to know width of each for future alignement
            ports = vhdl_util.clean_comment(m.group('port'))
            #print(ports)
            re_ports = r'''(?six)^[\ \t]*
                (?P<name>'''+self.s_id_list+r''')[\ \t]*:[\ \t]*
                (?P<dir>in|out|inout)[\ \t]+
                (?P<type>\w+)[\ \t]*
                (?P<range>\([^\)]*\)|range[\ \t]+[\w\-\+]+[\ \t]+(?:(?:down)?to)[\ \t]+[\w\-\+]+)?
                [\ \t]*(?P<end>;)?[\ \t]*(?:--(?P<comment>[^\n]*?))?$'''
            decl = re.findall(re_ports, ports ,flags=re.MULTILINE)
            name_len_l  = [] if not decl else [len(x[0].strip()) for x in decl]
            dir_len_l   = [] if not decl else [len(x[1].strip()) for x in decl]
            type_len_l  = [] if not decl else [len(x[2].strip()) for x in decl]
            range_len_l = [] if not decl else [len(x[3].strip()) for x in decl]
            name_len  = 0 if not name_len_l  else max(name_len_l )
            dir_len   = 0 if not dir_len_l   else max(dir_len_l  )
            type_len  = 0 if not type_len_l  else max(type_len_l )
            range_len = 0 if not range_len_l else max(range_len_l)
            all_range = [x[3] for x in decl if 'range' in x[3]]
            has_range = len(all_range)>0
            if has_range:
                range_len +=1

            #print(decl)
            comment_pos = name_len + type_len + range_len + dir_len+6
            #print('Length ports: N={} D={} T={} R={} => {}'.format(name_len,dir_len,type_len,range_len,comment_pos))

            # Add params with alignement and copy non params line as is
            txt_new += '{}port (\n'.format('\t'*(ilvl+1))
            for l in m.group('port').strip().splitlines() :
                mp = re.match(re_ports,l)
                if mp :
                    txt_new += '{ident}{name:<{length}} : '.format(ident='\t'*(ilvl+2),name=mp.group('name'),length=name_len)
                    txt_new += '{dir:<{length}} '.format(dir=mp.group('dir'),length=dir_len)
                    txt_new += '{type:<{length}}'.format(type=mp.group('type'),length=type_len)
                    if range_len>0 :
                        if mp.group('range') :
                            if 'range' in mp.group('range'):
                                txt_new += ' {range:<{length}}'.format(range=mp.group('range'),length=range_len-1)
                            else :
                                txt_new += '{range:<{length}}'.format(range=mp.group('range'),length=range_len)
                        else :
                            txt_new += ' '*(range_len)
                    txt_new += ';' if mp.group('end') else ' '
                    if mp.group('comment'):
                        txt_new += ' -- {}'.format(mp.group('comment').strip())
                else :
                    mc = re.match(self.s_comment,l)
                    if mc :
                        txt_new += '\t'*(ilvl+2)
                        pos = comment_pos if self.getIndentLevel(mc.group('space')) > (ilvl+2) else 0
                        txt_new += '{}{}'.format(' '*pos,mc.group(0).strip())
                    else :
                        #print('No port match for "{}"'.format(l))
                        txt_new += l
                txt_new += '\n'
            txt_new += '{});\n'.format('\t'*(ilvl+1))
        txt_new += '{}end;'.format('\t'*ilvl)

        #print(txt_new)
        return txt_new


    def alignInstance(self,txt,ilvl):
        m = re.match(r'(?si)(?P<emptyline>\n*)[ \t]*(?P<inst_name>\w+)\s*:\s*(?P<type>(?:entity\s+\w+\.)?\w+\b(?:\([\w\s]+\))?)\s*(?:(?P<gen_or_port>generic|port)\s+map)\s*\((?P<content>.*)\)\s*;',txt)
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
        txt_new += '\t'*(ilvl+1) + ');'
        return txt_new

    def alignInstanceBinding(self,txt,ilvl):
        # ensure one bind per line
        txt = re.sub(r',[ \t]*(\w+)',r',\n\1',txt.strip())
        re_bind = r'^\s*(?P<port>\w+(?:\s*\(./?\))?)\s*=>(?P<bind>.*?)(?P<sep>,?)(?P<comment>[ \t]*--.*)?$'
        bind = re.findall(re_bind,txt,flags=re.MULTILINE)
        ports = [len(x[0].strip()) for x in bind]
        port_len = 0 if not ports else max(ports)
        binds = [len(x[1].strip()) for x in bind]
        bind_len = 0 if not binds else max(binds)
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

