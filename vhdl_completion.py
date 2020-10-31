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

############################################################################
class VerilogAutoComplete(sublime_plugin.EventListener):

    def on_query_completions(self, view, prefix, locations):
        # don't change completion if we are not in a VHDL file
        if not view.match_selector(locations[0], 'source.vhdl'):
            return []
        # Init class members
        self.settings = view.settings()
        self.debug = self.settings.get("vhdl.debug")
        if self.settings.get("vhdl.disable_autocomplete", True):
            return []
        self.view = view
        # Completion only for first selection
        r = view.sel()[0]
        scope = view.scope_name(r.a)
        # If there is a prefix, allow sublime to provide completion ?
        flag = 0
        if(prefix==''):
            flag = sublime.INHIBIT_WORD_COMPLETIONS | sublime.INHIBIT_EXPLICIT_COMPLETIONS
        r, line, prev_word, prev_symb, scope_start = self.get_full_prefix(r,prefix)
        completion = []
        if self.debug:
            print('[VHDL::Autocomplete] prefix="{}" previous symbol="{}" previous word="{}" line="{}" scope={} / {}'.format(prefix,prev_symb,prev_word,line,scope,scope_start))
        if prev_symb == '.' :
        	completion = self.dot_completion(r)

        return (completion, flag)


    # Extract Full word and potentially symbol before completion request
    def get_full_prefix(self,r,prefix):
    	# Extract previous character and whole line before prefix
        prev_symb = ''
        prev_word = ''
        lr = sublime.Region(r.a,r.b)
        lr.a = self.view.find_by_class(lr.b,False,sublime.CLASS_LINE_START)
        l = self.view.substr(lr).strip()
        r.b -= len(prefix)
        r.a = r.b - 1
        tmp_r = sublime.Region(r.a,r.b)
        # print('[VHDL::Autocomplete.get_full_prefix] tmp_r={0} => "{1}" . Class = {2}'.format(tmp_r,self.view.substr(tmp_r),self.view.classify(tmp_r.b)))
        if not self.view.substr(tmp_r).strip() :
            tmp_r.b = self.view.find_by_class(tmp_r.b,False,sublime.CLASS_LINE_START | sublime.CLASS_PUNCTUATION_END | sublime.CLASS_WORD_END)
            tmp_r.a = tmp_r.b
        # if self.view.substr(tmp_r) in ['.','`','=','?']:
        if self.view.substr(tmp_r) in ['.']:
            prev_symb = self.view.substr(tmp_r)
        elif self.view.classify(tmp_r.b) & (sublime.CLASS_PUNCTUATION_END | 8192 | 4096):
            #print('[VHDL::Autocomplete.get_full_prefix] tmp_r={0} => "{1}" ==>'.format(tmp_r,self.view.substr(tmp_r)))
            tmp_r.a = self.view.find_by_class(tmp_r.b,False,sublime.CLASS_PUNCTUATION_START)
            # print('[VHDL::Autocomplete.get_full_prefix] (punct end) tmp_r={0} => "{1}" '.format(tmp_r,self.view.substr(tmp_r)))
            prev_symb = self.view.substr(tmp_r).strip()
            if not prev_symb :
                tmp_r.b = self.view.find_by_class(tmp_r.a,False,sublime.CLASS_LINE_START | sublime.CLASS_PUNCTUATION_END | sublime.CLASS_WORD_END)
                tmp_r.a = tmp_r.b
            else:
                if prev_symb[-1] == '.':
                    prev_symb = '.'
                    tmp_r.a = tmp_r.b - 1
                tmp_r.b = tmp_r.a
        if self.view.classify(tmp_r.b) & sublime.CLASS_WORD_END:
            tmp_r.a = self.view.find_by_class(tmp_r.b,False,sublime.CLASS_WORD_START)
            prev_word = self.view.substr(tmp_r).strip()
            tmp_r.b = tmp_r.a
            # print('[VHDL::Autocomplete.get_full_prefix] (word end) tmp_r={0} => "{1}" '.format(tmp_r,self.view.substr(tmp_r)))
        # Extract only last character for some symbol (typically to handle a parenthesis just before the operator)
        if prev_symb and prev_symb[-1] in ['.']:
            prev_symb = prev_symb[-1]
        scope_start = self.view.scope_name(tmp_r.a)
        return (r, l, prev_word, prev_symb, scope_start)


    def dot_completion(self,r):
        # select word before the dot and quit with no completion if no word found
        start_pos = r.a # save original position of the .
        start_word = self.view.substr(self.view.word(r))
        r.b = r.a
        r.a -=1

        array_depth = 0
        # Handle array case
        while self.view.substr(r) == ')' :
            r.a -=1
            r.b = r.a
            while self.view.substr(r) != '(' :
                r.a = self.view.find_by_class(r.a,False,sublime.CLASS_PUNCTUATION_START)
                r.b = r.a + 1
            r.b = r.a
            r.a -=1
            array_depth += 1

        r = self.view.word(r)
        w = str.rstrip(self.view.substr(r))
        scope = self.view.scope_name(r.a)
        completion = []
        if self.debug:
            print('[VHDL::dot_completion] previous word="{}" scope={} '.format(w,scope))
        if w=='' or 'entity.name.tag.library' in scope or 'invalid.illegal' in scope:
        	return completion

        # Check for multiple level of hierarchy
        cnt = 1
        autocomplete_max_lvl = 2 #self.settings.get("vhdl.autocomplete_max_lvl",2)
        while r.a>1 and self.view.substr(sublime.Region(r.a-1,r.a))=='.' and (cnt < autocomplete_max_lvl or autocomplete_max_lvl<0):
            # check previous char for array selection
            c = self.view.substr(sublime.Region(r.a-2,r.a-1))
            # Array selection -> extend to start of array
            if c == ')':
                r.a = self.view.find_by_class(r.a-3,False,sublime.CLASS_WORD_START)
                # print('[VHDL::dot_completion] Extending array selection -> {}'.format(view.substr(r)))
            if self.view.classify(r.a-2) & sublime.CLASS_WORD_START:
                r.a = r.a-2
            else :
                r.a = self.view.find_by_class(r.a-2,False,sublime.CLASS_WORD_START)
            cnt += 1
        if (cnt >= autocomplete_max_lvl and autocomplete_max_lvl>=0):
            print("[VHDL::dot_completion] Reached max hierarchy level for autocompletion. You can change setting vhdl.autocomplete_max_lvl")
            return completion
        w = str.rstrip(self.view.substr(r))
        txt = self.view.substr(sublime.Region(0, self.view.line(r).b))
        ti = vhdl_util.get_type_info(txt,w,4) # TODO: add function to retrieve type through multiple level of hierarchy
        if self.debug: print('[VHDL::dot_completion] Word = {} -> type = {}'.format(w,ti));
        if not ti or not ti['type'] or ti['type'] in ['std_logic','std_logic_vector','bit','bit_vector','string','integer','real','time','boolean']:
            return completion

        # Try to find type info: first in current file
        #check first in current file
        tti = vhdl_util.get_type_info(txt,ti['type'],4)
        if not tti or not tti['type']:
            filelist = self.view.window().lookup_symbol_in_index(ti['type'])
            # print(filelist);
            if filelist:
                file_ext = tuple(self.settings.get('vhdl.ext',['vhd','vhdl']))
                file_checked = []
                for f in filelist:
                    fname = sublime_util.normalize_fname(f[0])
                    if fname in file_checked:
                        continue
                    file_checked.append(fname)
                    if fname.lower().endswith(file_ext):
                        # print(w + ' of type ' + ti['type'] + ' defined in ' + str(fname))
                        tti = vhdl_util.get_type_info_file(fname,ti['type'],4)
                        if tti['type']:
                            break
        if self.debug: print('[VHDL::dot_completion] => type = {}'.format(tti));
        # print('[VHDL::dot_completion] => type = {}'.format(tti));
        if not tti or tti['type']!='record':
            return completion
        completion = self.record_completion(tti['decl'])
        return completion


    def record_completion(self,decl):
        c = []
        fti = vhdl_util.get_all_type_info_from_record(decl)
        for f in fti:
            f_type = f['type']
            m = re.search(r'\[.*\]', f['decl'])
            if m:
                f_type += m.group(0)
            c.append([f['name']+'\t'+f_type,f['name']])
        return c
