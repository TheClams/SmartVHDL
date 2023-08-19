# Class/function to process verilog file
import re, string, os
import pprint
import functools

# regular expression for signal/variable declaration:
s_id_list = r'\w+\b([\s\w,]+)?'
re_signal = r'(?i)^\s*(?P<tag>signal|variable)\s(?P<name>'+s_id_list+r'):\s*(?P<type>[^;]+)'
re_port   = r'(?i)^\s*(?P<name>'+s_id_list+r'):\s*(?P<port>in|out|inout)\s+(?P<type>[^;]+)'
re_generic = r'(?i)^\s*(?P<name>'+s_id_list+r'):\s*(?P<type>[\w\d\s\(\)]+)(?:\s*:=\s*(?P<value>[^;]+))?'
re_const  = r'(?i)^\s*(?P<tag>constant)\s(?P<name>'+s_id_list+r'):\s*(?P<type>[\w\d\s\(\)]+)\s*:=\s*(?P<value>[^;]+)'
re_record  = r'(?si)^\s*(?P<tag>type)\s(?P<name>'+s_id_list+r')\sis\s+(?P<type>record)\b(?P<content>.+?)(end\s+record)'
re_entity  = r'(?si)^\s*(?P<type>entity)\s+(?P<name>\w+)\s+is\s+\b(?P<content>.+?)(end)'
re_architecture = r'(?si)^\s*(?P<type>architecture)\s+(?P<tag>\w+)\s+of\s+(?P<name>\w+)\s+is\s+\b(?P<content>.+)(end)'
re_args = r'(?si)(?:^|;)\s*((?P<tag>signal|variable|constant)\s+)?(?P<name>'+s_id_list+r'):\s*((?P<dir>in|out|inout)\s+)?(?P<type>[^;]+)'

re_alias     = r'(?i)^\s*(?P<tag>alias)\s+(?P<name>\w+)\s*:\s*(?P<type>.*?)\bis\s+(?P<value>[^;]+)?'
re_alias_ref = r'(?i)^\s*(?P<tag>alias)\s+(?P<name>\w+)\s+is\s+<<(?P<value>.*?)>>\s*;'

###############################################################################
# Clean all comment (useful before parsing file for information)
def clean_comment(text):
    def replacer(match):
        s = match.group(0)
        if s.startswith('"'):
            return s
        else:
            return " " # note: a space and not an empty string

    pattern = re.compile(
        r'--.*?$|/\*.*?\*/|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE
    )
    return re.sub(pattern, replacer, text)

###############################################################################
# Extract declaration of var_name from a file
def get_type_info_file(fname,var_name, flag):
    # print("Parsing file " + fname + " for variable " + var_name)
    fdate = os.path.getmtime(fname)
    ti = get_type_info_file_cache(fname, var_name, fdate, flag)
    # print(get_type_info_file_cache.cache_info())
    return ti

@functools.lru_cache(maxsize=32)
def get_type_info_file_cache(fname, var_name, fdate, flag):
    with open(fname) as f:
        flines = f.read()
        ti = get_type_info(flines, var_name, flag)
    return ti

# Extract the declaration of var_name from txt
#return a dictionnary with full information
def get_type_info(txt,var_name, flag):
    txt = clean_comment(txt)
    txt = re.sub(r'(?si)^[ \t]*component\b.*?\bend\b.*?;','',txt) # remove component declaration
    re_list = []
    if flag & 1:
        re_list += [re_entity]
    if flag & 2:
        re_list += [re_architecture]
    if flag & 4:
        re_list += [re_signal, re_port, re_const, re_generic, re_record, re_alias, re_alias_ref]
    m = None
    for s in re_list:
        if '<tag>type' in s:
            re_s = s.replace(s_id_list,r'\s*{}\s*'.format(var_name),1)
        elif '<type>entity' in s or '<type>architecture' in s or '<tag>alias' in s:
            re_s = s.replace(r'<name>\w+','<name>' + var_name,1)
        else :
            re_s = s.replace(s_id_list,r'(?:,?\s*)\b' + var_name + r'\b(?:[\s\w,]+)?',1)
        # print(re_s)
        m = re.search(re_s, txt, flags=re.MULTILINE)
        if m:
            # print(m.groups())
            break
    ti = get_type_info_from_match(var_name,m)[0]
    return ti

# Extract all signal declaration
def get_all_type_info_from_record(decl):
    m = re.search(r'\brecord\s+(.*?)\bend',decl)
    if m is None:
        return []
    ti = []
    content = m.group(1)
    # print(content)
    r = re.compile(r'(?P<name>\w+)\s*:\s*(?P<type>[^;]+);\s*(--(?P<comment>.*?\n))?',flags=re.MULTILINE)
    for m in r.finditer(content):
        ti.append({'decl':m.group(0), 'type':m.group('type'), 'name':m.group('name'), 'tag':'field', 'value':None, 'comment':m.group('comment')})
    # pprint.pprint(ti, width=200)
    return ti


# Get type info from a match object
def get_type_info_from_match(var_name,m):
    ti_not_found = {'decl':None, 'type':None, 'name':var_name, 'tag':'', 'value':None}
    if not m:
        return [ti_not_found]
    # Prepare common type information
    d = {'decl': '', 'type': None, 'name': var_name, 'tag':'', 'value':None}
    if 'type' in m.groupdict() and m.group('type'):
        d['type'] = m.group('type')
    ti = []
    if 'tag' in m.groupdict() and m.group('tag'):
        d['tag'] = m.group('tag').lower()
        if d['tag'] == 'alias' and not d['type']:
            d['type'] = 'alias'
    elif 'port' in m.groupdict():
        d['tag'] = 'port'
        d['dir'] = m.group('port')
    else :
        d['tag'] = 'generic'
    if 'dir' in m.groupdict() and m.group('dir'):
        d['dir'] = m.group('dir').lower()
    if 'value' in m.groupdict():
        d['value'] = '' if not m.group('value') else m.group('value').strip()
    # For entity/architecture define decl and return
    if 'type' in d and d['type']:
        if d['type'].lower() == 'entity' :
            d['decl'] = 'entity {}'.format(d['name'])
            return [d]
        elif d['type'].lower() == 'architecture' :
            d['decl'] = 'architecture {} of {}'.format(d['tag'],d['name'])
            return [d]
    # Extract identifier list if no var name was specified
    if var_name=='':
        sig_l = m.group('name').replace(' ','').split(',')
    else:
        sig_l = [var_name]
    for sig in sig_l:
        ti.append(d)
        s = sig.strip()
        # Remove other signal from the declaration
        ti[-1]['decl'] = m.group(0).strip().replace(m.group('name'),s,1)
        ti[-1]['name'] = s
        if d['tag']== 'port':
            ti[-1]['decl'] = 'port ' + ti[-1]['decl']
            # remove trailing parenthesis for port
            if m.group(0).count('(') < m.group(0).count(')') :
                ti[-1]['decl'] = ti[-1]['decl'][::-1].replace(')','',1)[::-1]
                ti[-1]['type'] = ti[-1]['type'][::-1].replace(')','',1)[::-1]
                # print(ti[-1])
        # Cleanup multiple spaces
        ti[-1]['decl'] = re.sub(r'\s+',' ', ti[-1]['decl'] )
        ti[-1]['type'] = re.sub(r'\s+',' ', ti[-1]['type'])
    # print(ti)
    return ti

###############################################################################
# Parse an architecture for instance information
def get_inst_list_from_file(fname,mname=r'\w+'):
    # print("Parsing file " + fname + " for module " + mname)
    fdate = os.path.getmtime(fname)
    inst_l = get_inst_list_from_file_cache(fname, mname, fdate)
    # print(get_inst_list_from_file_cache.cache_info())
    return inst_l

@functools.lru_cache(maxsize=32)
def get_inst_list_from_file_cache(fname, mname, fdate):
    with open(fname) as f:
        flines = f.read()
        inst_l = get_inst_list(flines, mname)
    #if inst_l is None : print('[get_inst_list] No architecture for {} in {}'.format(mname,fname))
    return inst_l

# Retrieve the list of instances inside a block
def get_inst_list(txt,name):
    txt = clean_comment(txt)
    # Remove function/procedure to avoid the end;
    txt = re.sub(r'(?si)(function|procedure)\s+(\w+).*?\bend(?:\s+\1\b|\s+\2\b|\s*;)','',txt)
    re_str = r'(?si)^\s*architecture\s+(\w+)\s+of\s+'+name+r'\s+is.*?end(?:\s+architecture\b|\s+\1\b|\s*;)'
    m = re.search(re_str,txt,flags=re.MULTILINE)
    if not m:
        return None
    l = re.findall(r'(?si)^\s*(\w+)\s*:\s*entity\s+(?:\w+\.)?(\w+)\b',m.group(0),flags=re.MULTILINE)
    l += re.findall(r'(?si)^\s*(\w+)\s*:\s*(?:\w+\.)?(\w+)\s+(?:generic|port)\s+map\b',m.group(0),flags=re.MULTILINE)
    return l


###############################################################################
# Parse an entity/component for ports & generics information
def get_ports_file(fname,mname=r'\w+'):
    # print("Parsing file " + fname + " for module " + mname)
    fdate = os.path.getmtime(fname)
    minfo = get_ports_file_cache(fname, mname, fdate)
    # print(get_ports_file_cache.cache_info())
    return minfo

@functools.lru_cache(maxsize=32)
def get_ports_file_cache(fname, mname, fdate):
    with open(fname) as f:
        flines = f.read()
        minfo = get_ports(flines, mname)
    return minfo

def get_ports(flines,mname=r'\w+'):
    flines = clean_comment(flines)
    m = re.search(r"(?si)(?P<type>entity|component)\s+(?P<name>"+mname+r")\s+is\s+(generic\s*\((?P<generic>.*?)\)\s*;\s*)?(port\s*\((?P<port>.*?)\)\s*;)?\s*(?P<ending>end\b.*?);", flines, re.MULTILINE)
    if m is None:
        return None
    info = {'param': [], 'port': [], 'name':m.group('name'), 'type':m.group('type')}
    # print('Generics = {}\nPorts={}'.format(m.group('generic'),m.group('port')))
    if m.group('generic'):
        for mp in re.finditer(re_generic, m.group('generic')+';', flags=re.MULTILINE):
            info['param'] += get_type_info_from_match('',mp)
    if m.group('port'):
        for mp in re.finditer(re_port, m.group('port')+';', flags=re.MULTILINE):
            info['port'] += get_type_info_from_match('',mp)
    return info

###############################################################################
# Parse an architecture for all signals declaration

def get_signals(flines,name=r'\w+'):
    # Remove all comments
    flines = clean_comment(flines)
    # Find the signals declaration part and extract module & architecture name
    re_str = r'(?si)^\s*architecture\s+(?P<arch>\w+)\s+of\s+(?P<name>'+name+r')\s+is(?P<decl>.*?)\bbegin\b'
    m = re.search(re_str,flines, flags=re.MULTILINE)
    if m is None:
        return None
    info = {'name': m.group('name'), 'arch': m.group('arch') , 'signal':[], 'alias':[], 'const':[]}
    # Extract all signals
    for ms in re.finditer(re_signal, m.group('decl'), flags=re.MULTILINE):
        info['signal'] += get_type_info_from_match('',ms)
    for ms in re.finditer(re_alias, m.group('decl'), flags=re.MULTILINE):
        info['alias'] += get_type_info_from_match('',ms)
    for ms in re.finditer(re_alias_ref, m.group('decl'), flags=re.MULTILINE):
        info['alias'] += get_type_info_from_match('',ms)
    for ms in re.finditer(re_const, m.group('decl'), flags=re.MULTILINE):
        info['const'] += get_type_info_from_match('',ms)
    # print(info)
    return info


# Retrieve the list of functions inside a block
def get_function_list(txt,name, cleaned=False):
    if not cleaned:
        txt = clean_comment(txt)
    # Remove function/procedure to avoid the end;
    re_str_func = r'(?si)(?P<type>function)\s+(?P<name>\w+)\s*\((?P<args>.*?)\)\s*return(?P<ret>.*?)\b(?P<term>is)'
    info = {}
    for m in re.finditer(re_str_func,txt):
        n = m.group('name')
        if n in info:
            continue
        info[n] = {'return':m.group('name'), 'args': []}
        args = []
        for ma in re.finditer(re_args, m.group('args'), flags=re.MULTILINE):
            info[n]['args'] += get_type_info_from_match('',ma)
    # print(info)
    return info

# Retrieve the list of procedure inside a block
def get_procedure_list(txt,name, cleaned=False):
    if not cleaned:
        txt = clean_comment(txt)
    # Remove function/procedure to avoid the end;
    re_str_proc = r'(?si)(?P<type>procedure)\s+(?P<name>\w+)\s*\((?P<args>.*?)\)\s*(?P<term>is|;)'
    info = {}
    for m in re.finditer(re_str_proc,txt):
        n = m.group('name')
        if n in info:
            continue
        info[n] = {'args': []}
        # print(m.groups())
        for ma in re.finditer(re_args, m.group('args')+';', flags=re.MULTILINE):
            # print(ma.groups())
            info[n]['args'] += get_type_info_from_match('',ma)
    # print(info)
    return info

# Retrieve the list of process inside a block
def get_process_list(txt,name, cleaned=False):
    if not cleaned:
        txt = clean_comment(txt)
    # Remove function/procedure to avoid the end;
    re_str_proc = r'(?si)(?P<name>\w+)\s*:\s*(?P<type>process)'
    info = []
    for m in re.finditer(re_str_proc,txt):
        info.append(m.group('name'))
    return info
