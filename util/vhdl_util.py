# Class/function to process verilog file
import re, string, os
import pprint
import functools

# regular expression for signal/variable declaration:
s_id_list = r'\w+(\s*,[\s\w,]+)?'
re_signal = r'(?i)^\s*(?P<tag>signal|variable)\s+(?P<name>'+s_id_list+r')\s*:\s*(?P<type>[^;]+)'
re_port   = r'(?i)^\s*(?P<name>'+s_id_list+r')\s*:\s*(?P<port>in|out|inout)\s+(?P<type>[^;]+)'
re_generic = r'(?i)^\s*(?P<name>'+s_id_list+r')\s*:\s*(?P<type>[\w\d\s\(\)]+)(?:\s*:=\s*(?P<value>[^;]+))?'
re_const  = r'(?i)^\s*(?P<tag>constant)\s+(?P<name>'+s_id_list+r')\s*:\s*(?P<type>[\w\d\s\(\)]+)\s*:=\s*(?P<value>[^;]+)'

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
def get_type_info_file(fname,var_name):
    # print("Parsing file " + fname + " for variable " + var_name)
    fdate = os.path.getmtime(fname)
    ti = get_type_info_file_cache(fname, var_name, fdate)
    # print(get_type_info_file_cache.cache_info())
    return ti

@functools.lru_cache(maxsize=32)
def get_type_info_file_cache(fname, var_name, fdate):
    with open(fname) as f:
        flines = f.read()
        ti = get_type_info(flines, var_name)
    return ti

# Extract the declaration of var_name from txt
#return a dictionnary with full information
def get_type_info(txt,var_name):
    txt = clean_comment(txt)
    txt = re.sub(r'(?si)^[ \t]*component\b.*?\bend\b.*?;','',txt) # remove component declaration
    re_list = [re_signal, re_port, re_const, re_generic]
    for s in re_list:
        re_s = s.replace(s_id_list,r'(?:[\s\w,]+,\s*)?' + var_name + r'(?:\s*,[\s\w,]+)?',1) # TODO: handle case variable is part of a list
        m = re.search(re_s, txt, flags=re.MULTILINE)
        # print(re_s)
        if m:
            break
    ti = get_type_info_from_match(var_name,m)[0]
    return ti


# Get type info from a match object
def get_type_info_from_match(var_name,m):
    ti_not_found = {'decl':None, 'type':None, 'name':var_name, 'tag':'', 'value':None}
    if not m:
        return [ti_not_found]
    # Prepare common type information
    d = {'decl': '', 'type':m.group('type'), 'name': var_name, 'tag':'', 'value':None}
    # Extract identifier list if no var name was specified
    if var_name=='':
        sig_l = m.group('name').replace(' ','').split(',')
    else:
        sig_l = [var_name]
    ti = []
    if 'tag' in m.groupdict():
        d['tag'] = m.group('tag')
    elif 'port' in m.groupdict():
        d['tag'] = 'port'
        d['dir'] = m.group('port')
    else :
        d['tag'] = 'generic'
    if 'value' in m.groupdict():
        d['value'] = '' if not m.group('value') else m.group('value').strip()
    for sig in sig_l:
        ti.append(d)
        # Remove other signal from the declaration
        ti[-1]['decl'] = m.group(0).strip().replace(m.group('name'),sig,1)
        ti[-1]['name'] = sig
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
    #print(ti)
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
    info = {'name': m.group('name'), 'arch': m.group('arch') , 'signal':[]}
    # Extract all signals
    for m in re.finditer(re_signal, m.group('decl'), flags=re.MULTILINE):
        info['signal'] += get_type_info_from_match('',m)
    # print(info)
    return info
