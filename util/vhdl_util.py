# Class/function to process verilog file
import re, string, os
import pprint
import functools

# regular expression for signal/variable declaration:
s_id_list = r'\w+(\s*,[\s\w,]+)?'
re_signal = r'(?i)^\s*(?P<tag>signal|variable)\s+(?P<name>'+s_id_list+r')\s*:\s*(?P<type>[^;]+);'
re_port   = r'(?i)^\s*(?P<name>'+s_id_list+r')\s*:\s*(?P<port>in|out|inout)\s+(?P<type>[^;]+);'
re_const  = r'(?i)^\s*(?P<tag>constant)\s+(?P<name>'+s_id_list+r')\s*:\s*(?P<type>[\w\d\s\(\)]+)\s*:=\s*(?P<value>[^;]+);'

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
        r'//.*?$|/\*.*?\*/|"(?:\\.|[^\\"])*"',
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
    re_list = [re_signal, re_port, re_const]
    for s in re_list:
        re_s = s.replace(s_id_list,var_name,1) # TODO: handle case variable is part of a list
        m = re.search(re_s, txt, flags=re.MULTILINE)
        if m:
            break
    ti = get_type_info_from_match(var_name,m)[0]
    return ti


# Get type info from a match object
def get_type_info_from_match(var_name,m):
    ti_not_found = {'decl':None, 'type':None, 'name':var_name, 'tag':'', 'value':None}
    if not m:
        return [ti_not_found]
    # Extract identifier list if no var name was specified
    if var_name=='':
        sig_l = [var_name]
    else:
        sig_l = m.group('name').replace(' ','').split(',')
    ti = []
    # Prepare common type information
    d = {'decl': '', 'type':m.group('type'), 'name': '', 'tag':'', 'value':None}
    if 'tag' in m.groupdict():
        d['tag'] = m.group('tag')
    elif 'port' in m.groupdict():
        d['tag'] = 'port'
        d['dir'] = m.group('port')
    if d['tag'] in ['constant']:
        d['value'] = m.group('value')
    for sig in sig_l:
        ti.append(d)
        # Remove other signal from the declaration and cleanup multiple spaces
        ti[-1]['decl'] = re.sub(r'\s+',' ', m.group(0).strip().replace(m.group('name'),sig,1) )
        if d['tag']== 'port':
            ti[-1]['decl'] = 'port ' + ti[-1]['decl']
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
    return inst_l

# Retrieve the list of instances inside a block
def get_inst_list(txt,name):
    txt = clean_comment(txt)
    re_str = r'(?si)^\s*architecture\s+(\w+)\s+of\s+'+name+r'\s+is.*?end\s+(?:architecture|\1)\b'
    # print('[get_inst_list] regexp = {}'.format(re_str))
    m = re.search(re_str,txt,flags=re.MULTILINE)
    if not m:
        return []
    l = re.findall(r'(?si)^\s*(\w+)\s*:\s*entity\s+(?:\w+\.)?(\w+)\b',m.group(0),flags=re.MULTILINE)
    l += re.findall(r'(?si)^\s*(\w+)\s*:\s*(?:\w+\.)?(\w+)\s+(?:generic|port)\s+map\b',m.group(0),flags=re.MULTILINE)
    return l