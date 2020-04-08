import sublime, sublime_plugin
import re, string, os, sys, functools, mmap, imp

try:
    from .util import vhdl_util
    from .util import sublime_util
except ImportError:
    sys.path.append(os.path.join(os.path.dirname(__file__), "util"))
    import vhdl_util
    import sublime_util

# Make sure util pythons are reloaded
def plugin_loaded():
    imp.reload(vhdl_util)
    imp.reload(sublime_util)

list_module_files = {}
lmf_update_ongoing = False

############################################################################
# Helper functions
def lookup_type(view, t, flag):
    ti = None
    filelist = view.window().lookup_symbol_in_index(t)
    if filelist:
        # print(filelist)
        # Check if symbol is defined in current file first
        fname = view.file_name()
        flist_norm = [sublime_util.normalize_fname(f[0]) for f in filelist]
        if fname in flist_norm:
            _,_,rowcol = filelist[flist_norm.index(fname)]
            # print(t + ' defined in current file' + str(fname))
            ti = vhdl_util.get_type_info_file(fname,t, flag)
        if ti and ti['type'] and ti['tag']!='typedef' :
            ti['fname'] = (fname,rowcol[0],rowcol[1])
        # Consider first file with a valid type definition to be the correct one
        else:
            settings = view.settings()
            file_ext = tuple(settings.get('vhdl.ext',["vhd","vhdl" ]))
            for f in filelist:
                fname, display_fname, rowcol = f
                fname = sublime_util.normalize_fname(fname)
                # print('Parsing ' + str(fname))
                if fname.lower().endswith(file_ext):
                    ti = vhdl_util.get_type_info_file(fname,t, flag)
                    # print(ti)
                    if ti['type'] and ti['tag']!='typedef' :
                        ti['fname'] = (fname,rowcol[0],rowcol[1])
                        break
    # print('[VHDL:lookup_type] {0}'.format(ti))
    return ti


########################################
# Create module instantiation skeleton #
class VhdlModuleInstCommand(sublime_plugin.TextCommand):

    #TODO: Run the search in background and keep a cache to improve performance
    def run(self,edit):
        global list_module_files
        if len(self.view.sel())>0 :
            r = self.view.sel()[0]
            scope = self.view.scope_name(r.a)
            if 'meta.module.inst' in scope:
                self.view.run_command("vhdl_module_reconnect")
                return
        self.window = sublime.active_window()
        # Populate the list_module_files:
        #  - If no folder in current project, just list open files
        #  - if it exist use latest version and display panel immediately while running an update
        #  - if not display panel only when list is ready
        projname = self.window.project_file_name()
        if not sublime.active_window().folders():
            list_module_files['__NONE__'] = []
            for v in self.window.views():
                if v and v.file_name():
                    list_module_files['__NONE__'].append(os.path.abspath(v.file_name()))
            self.on_list_done('__NONE__')
        elif projname not in list_module_files:
            sublime.set_timeout_async(functools.partial(self.get_list_file,projname,functools.partial(self.on_list_done,projname)), 0)
            sublime.status_message('Please wait while module list is being built')
        elif not lmf_update_ongoing:
            # Create a copy so that the background update does not change the content of the list
            list_module_files['__COPY__'] = list_module_files[projname][:]
            # Start background update of the list
            sublime.set_timeout_async(functools.partial(self.get_list_file,projname), 0)
            # Display quick panel
            self.on_list_done('__COPY__')

    def get_list_file(self, projname, callback=None):
        global list_module_files
        global lmf_update_ongoing
        lmf_update_ongoing = True
        lmf = []
        for folder in sublime.active_window().folders():
            for root, dirs, files in os.walk(folder):
                for fn in files:
                    if fn.lower().endswith(('.vhd','.vho','.vhdl')):
                        ffn = os.path.join(root,fn)
                        f = open(ffn)
                        if os.stat(ffn).st_size:
                            s = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                            if s.find(b'entity') != -1:
                                lmf.append(ffn)
                            elif s.find(b'component') != -1:
                                lmf.append(ffn)
        sublime.status_message('List of module files updated')
        list_module_files[projname] = lmf[:]
        lmf_update_ongoing = False
        if callback:
            callback()

    def on_list_done(self,projname):
        self.window.show_quick_panel(list_module_files[projname], functools.partial(self.on_select_file_done,projname))

    def on_select_file_done(self, projname, index):
        if index >= 0:
            fname = list_module_files[projname][index]
            try:
                with open(fname, "r") as f:
                    flines = str(f.read())
                self.ml=re.findall(r'^\s*entity\s+(\w+)\s+is',flines,re.MULTILINE);
                if len(self.ml)<2:
                    self.view.run_command("vhdl_do_module_parse", {"args":{'fname': fname, 'mname':r'\w+'}})
                else:
                    sublime.set_timeout_async(lambda: self.window.show_quick_panel(self.ml, functools.partial(self.on_select_module_done,fname)),0)
            except FileNotFoundError:
                print('[Smart VHDL] File {} not found for module instantiation'.format(fname))

    def on_select_module_done(self, fname, index):
        if index >= 0:
            self.view.run_command("vhdl_do_module_parse", {"args":{'fname': fname, 'mname':self.ml[index]}})

# Parse a module declaration for port and generics
# Optionnaly ask user a value for each generics
class VhdlDoModuleParseCommand(sublime_plugin.TextCommand):

    def run(self, edit, args):
        self.fname = args['fname']
        self.minfo = vhdl_util.get_ports_file(self.fname, args['mname'])
        # print(self.minfo)
        if self.minfo is not None:
            self.param_value = []
            settings = self.view.settings()
            self.generic_explicit = settings.get('vhdl.generic_explicit',False)
            if settings.get('vhdl.instance_as_snippet',False):
                for p in self.minfo['param']:
                    self.param_value.append({'name':p['name'] , 'value': p['value']});
            if self.minfo['param'] and settings.get('vhdl.generic_fill') and not settings.get('vhdl.instance_as_snippet',False):
                self.cnt = 0
                self.show_prompt()
            else:
                self.view.run_command("vhdl_do_module_inst", {"args":{'minfo':self.minfo, 'pv':self.param_value, 'fname':self.fname}})

    # Prompt user for a generic value
    def show_prompt(self):
        p = self.minfo['param'][self.cnt]
        default = '' if not p['value'] else 'Default: {0}'.format(p['value'])
        name = '{} ({})'.format(p['name'],p['type'])
        panel = sublime.active_window().show_input_panel(name, default, self.on_prompt_done, None, None)
        #select the whole line (to ease value change)
        r = panel.line(panel.sel()[0])
        panel.sel().clear()
        panel.sel().add(r)

    # When user has entered a generic value, called again the prompt if this is not the last generic
    # Otherwise do the actual instantiation
    def on_prompt_done(self, content):
        if not content.startswith("Default"):
            self.param_value.append({'name':self.minfo['param'][self.cnt]['name'] , 'value': content});
        elif self.generic_explicit :
            self.param_value.append({'name':self.minfo['param'][self.cnt]['name'] , 'value': content[9:]});
        self.cnt += 1
        if not self.minfo['param']:
            return
        if self.cnt < len(self.minfo['param']):
            self.show_prompt()
        else:
            self.view.run_command("vhdl_do_module_inst", {"args":{'minfo':self.minfo, 'pv':self.param_value, 'fname':self.fname}})


# Actual Module instantiation
class VhdlDoModuleInstCommand(sublime_plugin.TextCommand):

    def run(self, edit, args):
        settings = self.view.settings()
        minfo = args['minfo']
        params = args['pv']
        # retrieve connection
        (decl,ac,wc) = self.get_connect(self.view,settings,minfo)
        # print('decl = {}\nAC = {}\nwc = {}'.format(decl,ac,wc))
        # Instance name
        is_snippet = settings.get('vhdl.instance_as_snippet',False)
        inst = '\t'
        cnt = 1
        if is_snippet :
            inst+= '${{{}:'.format(cnt)
            cnt += 1
        inst += settings.get('vhdl.instance_prefix','') + minfo['name'] + settings.get('vhdl.instance_suffix','')
        if is_snippet :
            inst+= '}'
        inst += ' : entity work.{}\n'.format(minfo['name'])
        # Generic Map
        if params :
            inst += '\t\tgeneric map (\n'
            max_len_l = max([len(x['name']) for x in params])
            max_len_r = max([len(x['value']) for x in params])
            for i,param in enumerate(params) :
                inst += '\t\t\t{} => '.format(param['name'].ljust(max_len_l))
                if is_snippet :
                    inst+= '${{{}:'.format(cnt)
                    cnt += 1
                inst += param['value'].ljust(max_len_r)
                if is_snippet :
                    inst+= '}'
                if i<len(params)-1:
                    inst +=','
                inst += '\n'
            inst += '\t\t)\n'
        # Port Map
        if minfo['port'] :
            inst += '\t\tport map (\n'
            max_len_l = max([len(x['name']) for x in minfo['port']])
            max_len_r = 0 if not ac else max([len(x) for x in ac])
            for i,port in enumerate(minfo['port']) :
                inst += '\t\t\t{} => '.format(port['name'].ljust(max_len_l))
                if is_snippet :
                    inst+= '${{{}:'.format(cnt)
                    cnt += 1
                inst += '' if port['name'] not in ac else ac[port['name']].ljust(max_len_r)
                if is_snippet :
                    inst+= '}'
                # Remove entry of ac if it is the same as the port (to be used by the final report)
                if port['name'] in ac and ac[port['name']] == port['name']:
                    ac.pop(port['name'],0)
                if i<len(minfo['port'])-1:
                    inst +=','
                inst += '\n'
            inst += '\t\t)'
        inst += ';\n\n'
        report = ''
        # Insert code for module Instantiation
        if is_snippet:
            self.view.run_command('insert_snippet',{'contents':inst})
        else :
            self.view.insert(edit, self.view.line(self.view.sel()[0]).a, inst)
        # Insert signal declaration if any
        if decl and not is_snippet:
            r_start = self.view.find(r'(?si)^\s*architecture\s+\w+\s+of\s+\w+\s+is(.*?)$',0, sublime.IGNORECASE)
            if r_start:
                # print('Start = {} = {} '.format(r_start,self.view.substr(r_start)))
                # find position of last ;
                r_begin = self.view.find(r'(?si)\bbegin\b',r_start.b, sublime.IGNORECASE)
                r_begin2 = self.view.find(r'(?si);[^;]+\bbegin\b',r_start.b, sublime.IGNORECASE)
                # print(' -> end = {} & {}'.format(r_begin,r_begin2))
                if r_begin2.a > 0 and r_begin2.a < r_begin.a - 1 :
                    r_start.a = r_begin2.a+1
                elif r_begin.a > 0 and r_start.b < r_begin.a - 1 :
                    r_start.a = r_begin.a-1
                else:
                    r_start.a = r_start.b
                # print(' => Start = {}'.format(r_start))
                self.view.insert(edit, r_start.a, '\n'+decl)
                report += 'Declaring {} signals\n'.format(len(decl.splitlines()))
            else :
                report += 'Unable to find declaration region:\n' + decl
        if len(ac)>0 :
            report+= 'Non-perfect name match for {} port(s) : {}\n'.format(len(ac),ac)
        if len(wc)>0 :
            report+= 'Found {} mismatch(es) for port(s): {}\n'.format(len(wc),[x for x in wc.keys()])
        if report:
            sublime_util.print_to_panel(report,'SmartVHDL')

    # Find connection between instance port and local signal/port
    def get_connect(self,view,settings,minfo):
        decl = ''
        ac = {} # autoconnection (entry is port name)
        wc = {} # warning connection (entry is port name)
        if not settings.get('vhdl.autoconnect',False) or not minfo['port']:
            return (decl,ac,wc)
        port_prefix = settings.get('vhdl.autoconnect_port_prefix', [])
        port_suffix = settings.get('vhdl.autoconnect_port_suffix', [])
        # Find local signals and port for connection
        txt = self.view.substr(sublime.Region(0, self.view.size()))
        info = vhdl_util.get_signals(txt)
        if not info:
            return (decl,ac,wc)
        port_info = vhdl_util.get_ports(txt)
        # TODO: handle case where entity is defined in another file ...
        if not port_info:
            pass
        # Merge signal and port information into one dict
        if port_info :
            info['port'] = port_info['port']
            info['param'] = port_info['param']
        # Create a dictionnay of all port and signal
        dict_sig = {x['name']: x for x in info['port']}
        dict_sig.update({x['name']: x for x in info['signal']})
        dict_sig_txt = '\n'.join(dict_sig.keys())
        if info['param']:
            dict_param = {x['name']: x for x in info['param']}
        # For each port of the instance, find an existing port/signal to connect
        # If not create a new signal and provide its declaration
        for port in minfo['port']:
            #Remove suffix/prefix of port name
            pname = port['name']
            for prefix in port_prefix:
                if pname.startswith(prefix):
                    pname = pname[len(prefix):]
                    break
            for suffix in port_suffix:
                if pname.endswith(suffix):
                    pname = pname[:-len(suffix)]
                    break
            # Check existing signals/port
            ti = {'decl':None,'type':None, 'name':pname, 'tag':'signal'}
            if pname in dict_sig:
                ti = dict_sig[pname]
                _,warn = self.check_connect(port,ti)
            # Check for extended match: prefix
            if not ti['decl']:
                if settings.get('vhdl.autoconnect_allow_prefix',False):
                    sl = re.findall(r'\b(\w+_'+pname+r')\b',dict_sig_txt,flags=re.MULTILINE)
                    if sl :
                        # find smallest signal matching type of port
                        sl.sort(key = lambda s: len(s))
                        for sn in sl:
                            ti = dict_sig[sn]
                            _,warn = self.check_connect(port,ti)
                            if not warn:
                                break
            # Check for extended match: suffix
            if not ti['decl']:
                if settings.get('vhdl.autoconnect_allow_suffix',False):
                    sl = re.findall(r'\b('+pname+r'_\w+)\b',dict_sig_txt,flags=re.MULTILINE)
                    if sl :
                        # find smallest signal matching type of port
                        sl.sort(key = lambda s: len(s))
                        for sn in sl:
                            ti = dict_sig[sn]
                            _,warn = self.check_connect(port,ti)
                            if not warn:
                                break
            # Create a declaration when a new signal has to be created
            if not ti['decl']:
                d,warn = self.check_connect(port,ti)
                decl += '\t{}\n'.format(d) # Add signal declaration with basic indentation (find local indentation ?)
            if warn:
                wc[port['name']] = warn
            # Set signal name for autoconnect information
            ac[port['name']] = ti['name']
        return (decl,ac,wc)

    def check_connect(self,port,sig):
        d = re.sub(r'(?i)^\s*port\b','signal',port['decl'])
        d = re.sub(r'(?i)\b(in|out|inout)\s+',' ',d)
        warn = ''
        if sig['decl']:
            ds = sig['decl'].lower()
            if sig['tag']=='port':
                ds = re.sub(r'(?i)^\s*port\b','signal',ds).lower()
                ds = re.sub(r'(?i)\s+(in|out|inout)\s+',' ',ds)
                if sig['dir']!=port['dir']:
                    warn = 'Incompatible port direction'
            ds = re.sub(r'\b'+sig['name']+r'\b',port['name'],ds)
            if not warn and d.lower()!=ds:
                warn = 'Signal/port not matching: "{}" vs  "{}"'.format(port['decl'],sig['decl'])
        d += ';'
        return d,warn
