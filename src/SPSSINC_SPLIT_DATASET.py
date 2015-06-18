from __future__ import with_statement

"""SPSSINC SPLIT DATASET extension command"""
#Licensed Materials - Property of IBM
#IBM SPSS Products: Statistics General
#(c) Copyright IBM Corp. 2010, 2014
#US Government Users Restricted Rights - Use, duplication or disclosure 
#restricted by GSA ADP Schedule Contract with IBM Corp.
__author__ =  'spss, JKP'
__version__=  '1.2.2'

# history
# 08-feb-2010 original version
# 31-mar-2010 expand file handles for file list log if V18 or later
# 24-jan-2011 allow multiple split variables and patterns in directory paths
# 08-feb-2011 add FILENAMESUBS keywordf
# 07-mar-2011 file handle support in DIRECTORY keyword in class Filename
# 09-dec-2011 bug fix for delete
# 23-jul-2013 prevent multiple missing value definitions from causing file conflict

helptext = """SPSSINC SPLIT DATASET
SPLITVAR=variable-names
/OUTPUT
[DIRECTORY="directory-specification-for-output"] [DELETECONTENTS={NO* | YES}] 
[MAKETEMPDIR={NO* | YES}]] [FILENAME="filename"]
[/OPTIONS [NAMES={VALUES*|LABELS|NUMBERS}] FILENAMESUBS={ASDIR* | VALUES | LABELS}
[NAMEPREFIX="nameprefix"]
[PRINTLIST={YES* | NO}
[FILELIST="filespec"]]
[/HELP]

This command writes a collection of datasets with all the cases for each value of the split variable(s)
in a different dataset.  It facilitates executing arbitrary blocks of syntax for each distinct split value.
The extension command SPSSINC PROCESS FILES can be used to apply syntax to each of the
files written by this command.

Example:
spssinc split dataset splitvar= educ
/output directory="c:/temp/target" deletecontents=yes
/options names=values filelist="c:/temp/target/files.txt" printlist=yes.

Data do not need to be sorted by the split variable for this command.

The output file name is by default constructed from the variable values or labels
with an underscore(_) between parts if multiple variables are used.
FILENAME can be used to override these names.  It can be a pattern such as
described below for directories.  It is always given an sav extension.

System-missing values are written to a dataset named $Sysmis.sav.
A blank string value will be written to a dataset named .sav  (no rootname).
Such names are legal, but on some operating systems a directory listing will not show
names starting with a period by default.

SPLITVAR names one or more string or numeric variables that define the splits.  
If numeric, the values must be integers.

DIRECTORY optionally names a directory for the output.  If not specified, the current
working directory for the SPSS Processor is used.  The specified directory will be created
if it does not already exist.

The directory can be a simple path such as "c:\project\splits" or it can refer to some or
all of the variables used in splitting.  To refer to a variable value, use the variable name
in the path like this "${varname}".  For example, if splitting by variables xvar and yvar,
you could write
DIRECTORY = "c:/mydata/abc${xvar}/${yvar}".  if xvar has values "xyz" and "KLM" and
yvar has values 1 and 2, then directories
c:/mydata/abcxyz/1, c:/mydata/abcxyz/2, c:/mydata/abcKLM/1, and c:/mydata/abcKLM/2
could be created and used.  Only value combinations actually occurring in the data will
be created or used.  
Notes: 
- On a case-insensitive file system such as used by Windows,
the files created could be different from other systems.
- Characters typically not allowed in directory names are replaced with underscores (_).
These are  " * ? < > |

If MAKETEMPDIR is specified, a new temporary directory is created and used for the
output.  DIRECTORY must not be specified if this option is used.

DELETECONTENTS specifies whether all  SPSS sav files are removed before new files are
written.  Use with caution!  It cannot be used if DIRECTORY is not specified.  If the directory specification
includes variable substitutions, only directory references for values in the dataset being split
will be cleared.

NAMES can specify VALUES, the default, or LABELS or NUMBERS.  It determines how
the output directories and files are named.  For VALUES the file names are like value.sav, 
for LABELS, the file names are the label.sav; for numbers, the file names are sequential numbers.
If NAMES=NUMBERS and there is a directory pattern, the variable values are used
to expand that pattern.  The NAMES setting determines whether values or labels are
displayed in the detailed output pivot table.

Characters in the values or labels that would be illegal in a file name, including those listed
above and / or \, are replaced by the underscore character (_).  
If using LABELS, the value is used if there is no label.

By default, the same NAMES choice is used for file names.  You can override this by
specifying FILENAMESUBS = VALUES or LABELS.

If NAMEPREFIX is specified, that text plus _ will be prefixed to the output file names.
NAMEPREFIX cannot be combined with FILENAME.

If specified, FILELIST names a file that will contain a list of all the files that were written
along with the associated values.  This file can be used as input to SPSSINC PROCESS FILES.
If file handles are in use, the paths in the log are expanded to the true names if using V18
or later, but Viewer output is left in terms of the handles

/HELP displays this help and does nothing else.
"""

# Notes: V17 max XSAVES is 10.  V18 is 64.

import spss, spssaux
from extension import Template, Syntax, processcmd
import sys, locale, tempfile, random, os, glob, re, codecs, string


v18okay = spssaux.getSpssMajorVersion() >= 18
v19okay = spssaux.getSpssMajorVersion() >= 19

# Version 18 has a bug related to inserting Unicode text in a pivot table data cell.
# The following code monkey patches the problematic method just for V18 and earlier

if not v19okay:
    from spss import CellText, Dimension
    import time, datetime
    
    def SimplePivotTable(self,rowdim="",rowlabels=[],coldim="",collabels=[],cells=None):
        """Monkey Patch for unicode-in-cells bug for V18 and earlier"""

        error.Reset()

        try:
            # If cells is None, neither rowlabels nor collabels is allowed.
            if cells is None:
                if len(rowlabels) > 0:
                    error.SetErrorCode(1032)
                    if error.IsError():
                        raise SpssError,error
                elif len(collabels) > 0:
                    error.SetErrorCode(1032)
                    if error.IsError():
                        raise SpssError,error

            # Make a local copy. We don't want to change the original labels.
            tmpRowLabels = list(rowlabels)
            tmpColLabels = list(collabels)
        except TypeError:
            error.SetErrorCode(1004)
            if error.IsError():
                raise SpssError,error

        # Check the structure of cells.
        nRows = 0
        nCols = 0

        # None or empty cells is okay at this point.
        if cells is not None:
            nRows = len(cells)
            if nRows > 0:
                if not isinstance(cells[0],str):
                    try:
                        #check if cells[0] is iterable.
                        nCols = len([(i, x) for (i,x) in enumerate(cells[0])])
                    except TypeError:
                        nCols = 1
                else:
                    nCols = 1

        if tmpRowLabels <> [] and tmpColLabels <> []:
            nRows = len(tmpRowLabels)
            nCols = len(tmpColLabels)
        elif tmpRowLabels <> []:
            nRows = len(tmpRowLabels)
            # If there are no labels for the column dimension, the length of the first cells item is used.
            tmpColLabels.extend(["col"+str(x) for x in range(nCols)])
        elif tmpColLabels <> []:
            nCols = len(tmpColLabels)
            # If there are no labels for the row dimension, the number of rows in Cells is used.
            tmpRowLabels.extend(["row"+str(x) for x in range(nRows)])
        else:
            tmpRowLabels.extend(["row"+str(x) for x in range(nRows)])
            tmpColLabels.extend(["col"+str(x) for x in range(nCols)])

        tmpRowLabels = map(CellText._CellText__ToCellText,tmpRowLabels)
        tmpColLabels = map(CellText._CellText__ToCellText,tmpColLabels)

        tmpCells = []

        # cells must match the label structure if the labels are given.
        if nRows > 0 and nCols > 0:
            try:
                # Check cells length and if cells can be indexed as cells[i][j] or cells[i].
                if nCols > 1:
                    try:
                        x = []
                        for c in cells:
                            if isinstance(c, (tuple,list)):
                                x.append(len(c))
                            else:
                                x.append(1)
                        maxlen = max(x)
                    except TypeError:
                        maxlen = 1
                    if ( 1 == maxlen ):
                        assert (len(cells) == nCols * nRows)
                        tmpCells = [cells[x*nCols + y] for x in range(nRows) for y in range(nCols)]
                    else:
                        assert(maxlen == nCols)
                        assert(len(cells) == nRows)
                        tmpCells = [cells[x][y] for x in range(nRows) for y in range(nCols)]
                else:
                    assert(len(cells) == nCols * nRows)
                    tmpCells = [cells[x*nCols + y] for x in range(nRows) for y in range(nCols)]
            except:
                error.SetErrorCode(1032)
                if error.IsError():
                    raise SpssError, error

        # Check if cells[i][j] or cells[i] is scalar (such as sequence).
        for x in tmpCells:
            ###if not isinstance(x,(str, time.struct_time, datetime.datetime, datetime.date)):
            if not isinstance(x,(basestring, time.struct_time, datetime.datetime, datetime.date)):
                try:
                    [(i, x) for (i,x) in enumerate(x)]
                    error.SetErrorCode(1032)
                    if error.IsError():
                        raise SpssError, error
                except TypeError:
                    pass

        tmpCells = map(CellText._CellText__ToCellText,tmpCells)

        # If dimension is empty, the dimension label is hidden.
        if rowdim == "":
            rowdim = self.Append(Dimension.Place.row,"rowdim",True,False)
        else:
            rowdim = self.Append(Dimension.Place.row,rowdim,False,False)
        if coldim == "":
            coldim = self.Append(Dimension.Place.column,"coldim",True,False)
        else:
            coldim = self.Append(Dimension.Place.column,coldim,False,False)

        if tmpCells <> []:
            categories = [(row,col) for row in tmpRowLabels for col in tmpColLabels]
            for (i,cats) in enumerate(categories):
                self[cats] = tmpCells[i]

    # monkey patch BasePivotTable class
    import spss.errMsg
    error = spss.errMsg.errCode()
    spss.BasePivotTable.SimplePivotTable = SimplePivotTable


def _safeval(val, quot='"'):
    "return safe value for quoting with quot, which may be single or double quote or blank"
    return quot == " " and val or val.replace(quot, quot+quot)

def Run(args):
    """Execute the SPSSINC SPLIT DATASETS extension command"""

    args = args[args.keys()[0]]

    oobj = Syntax([
        Template("SPLITVAR", subc="",  ktype="existingvarlist", var="varnames", islist=True),
        Template("DIRECTORY", subc="OUTPUT", ktype="literal", var="directory"),
        Template("DELETECONTENTS", subc="OUTPUT", ktype="bool", var="deletecontents"),
        Template("MAKETEMPDIR", subc="OUTPUT", ktype="bool", var="maketempdir"),
        Template("FILENAME", subc="OUTPUT", ktype="literal", var="fnspec"),
        Template("NAMES", subc="OPTIONS", ktype="str", var="names", vallist=["values", "labels","numbers"]),
        Template("FILENAMESUBS", subc="OPTIONS", ktype="str", var="filenamesubs", vallist=["values", "labels", "numbers", "asdir"]),
        Template("NAMEPREFIX", subc="OPTIONS", ktype="literal", var="nameprefix"),
        Template("FILELIST", subc="OPTIONS", ktype="literal", var="filelist"),
        Template("PRINTLIST", subc="OPTIONS", ktype="bool", var="printlist"),
        Template("HELP", subc="", ktype="bool")])

    #try:
        #import wingdbstub
        #if wingdbstub.debugger != None:
            #if wingdbstub.debugger.ChannelClosed():
                #import time
                #wingdbstub.debugger.StopDebug()
                #time.sleep(2)
                #wingdbstub.debugger.StartDebug()
            #import thread
            #wingdbstub.debugger.SetDebugThreads({thread.get_ident(): 1}, default_policy=0)
    #except:
        #pass

    #enable localization
    global _
    try:
        _("---")
    except:
        def _(msg):
            return msg
    # A HELP subcommand overrides all else
    if args.has_key("HELP"):
        #print helptext
        helper()
    else:
        processcmd(oobj, args, makesplits, vardict=spssaux.VariableDict())

def helper():
    """open html help in default browser window
    
    The location is computed from the current module name"""

    import webbrowser, os.path
    
    path = os.path.splitext(__file__)[0]
    helpspec = "file://" + path + os.path.sep + \
         "markdown.html"
    
    # webbrowser.open seems not to work well
    browser = webbrowser.get()
    if not browser.open_new(helpspec):
        print("Help file not found:" + helpspec)
try:    #override
    from extension import helper
except:
    pass

def makesplits(varnames, directory=None, deletecontents=False, maketempdir = False,
               names="values", nameprefix="", filelist=None, printlist=True, fnspec="", filenamesubs="asdir"):
    """Create split data files and reports"""

    myenc = locale.getlocale()[1]  # get current encoding in case conversions needed
    if fnspec and nameprefix:
        raise ValueError(_("FILENAME and NAMEPREFIX cannot be used together"))
    if fnspec and names == "numbers":
        raise ValueError(_("FILENAME and Names = Numbers cannot be used together"))

    def unicodeit(value, keepnumeric=False):
        """Convert singleton or sequence to Unicode

        if keepnumeric, then numbers are left as numeric"""

        isseq = spssaux._isseq(value)
        if not isseq:
            value = [value]
        for i, v in enumerate(value):
            if isinstance(v, (int, float)):
                if not keepnumeric:
                    value[i]=  unicode(v)
            elif v is None:
                pass
            elif not isinstance(v, unicode):
                value[i] = unicode(v, myenc)
        if isseq:
            return value
        else:
            return value[0]

    cwd = unicodeit(spssaux.GetSHOW("DIRECTORY"))

    # output files will go into or under a temporary directory, the cwd of the backend,
    # or a specified path.  Deleting contents is not allowed in cwd.

    #if spssaux._isseq(varname):
        #varname = varname[0]
    varnames = unicodeit(varnames)
    directory = unescape(directory)
    root = None
    delcount = 0
    if maketempdir:
        root=tempfile.mkdtemp()
    elif directory is None:
        root = cwd
    elif  deletecontents:   # Needs update for subtrees
        if not directory.endswith("/") or directory.endswith("\\"):
            directory = directory + os.sep

    if directory and root:
        directory = os.path.join(root, directory)
    elif root:
        directory = root
    directory = unicodeit(directory)

    dsn = spss.ActiveDataset()
    if dsn == "*":
        dsn = "D" + str(random.uniform(0,1))
        spss.Submit("DATASET NAME " + dsn)

    varnamestr = " ".join(varnames)
    # get the list of values for the splitting variable.
    # AGGREGATE will fail if there are any undefined variables
    
    dsname = "D" + str(random.uniform(0,1))
    cmd = """DATASET DECLARE %(dsname)s.
    AGGREGATE /OUTFILE = "%(dsname)s"
    /BREAK = %(varnamestr)s
    /%(dsname)s=N.
    DATASET ACTIVATE %(dsname)s.""" % locals()
    spss.Submit(cmd)

    # cases is a list of tuples of values and counts.
    # By default, user missing values become None and can produce
    # multiple cases with the same apparent break value, so we turn that off.
    cur = spss.Cursor()
    cur.SetUserMissingInclude(True)
    cases = cur.fetchall()
    cur.close()
    spss.Submit("""DATASET CLOSE %(dsname)s.
DATASET ACTIVATE %(dsn)s.""" % locals())            

    # get all but last variable and convert from tuple to list
    cases = [list(item[:-1]) for item in cases]   # we just need the break values
    if names == "labels" or filenamesubs == "labels":
        vardict = spssaux.VariableDict(varnames)
        if len(vardict) != len(varnames):
            raise ValueError(_("One or more of the split variables was not found.  Note that names are case sensitive"))
        vldict = [vardict[v.VariableName].ValueLabels for v in vardict]  # a list of value label dictionaries
        # ensure that everything is properly unicoded
        vldict = [dict((unicodeit(k), unicodeit(v)) for k, v in item.iteritems()) for item in vldict]
    else:
        vldict = [{}]

    # set up values for use in syntax by quoting and converting values


    for row, case in enumerate(cases):
        for v, vval in enumerate(case):
            if not isinstance(vval, basestring) and vval is not None:
                if int(vval) != vval:
                    raise ValueError(_("Split variable contains non-integer value: %f") % vval)


    valuecount = len(cases)

    fnc = filename(varnames, names, vldict, directory, nameprefix, myenc, unicodeit, 
                   deletecontents, fnspec, filenamesubs)
    xsavetemplate = """  XSAVE OUTFILE=%s."""

    xsavelimit = v18okay and 64 or 10

    remaining = valuecount
    fns = []

    for v in range(0, valuecount, xsavelimit):
        if v > 0:
            spss.Submit("EXECUTE.")   # must execute transformation block in order to submit new ones
        for g in range(min(xsavelimit, remaining)):
            if g == 0:
                cmd = ["DO IF "]
            else:
                cmd.append("ELSE IF ")
            values = unicodeit(cases[v+g], keepnumeric=True)
            spssexpr = makeexpr(varnames, values)
            cmd[-1] = cmd[-1] + ("(" + spssexpr + ").")
            valuestr, fnv, fn, thefile = fnc.genfn(values)
            fns.append([fn, valuestr, thefile])
            cmd.append(xsavetemplate % fn)
        cmd.append("END IF.")
        spss.Submit("\n".join(cmd))
        remaining -= xsavelimit


    for i in range(valuecount):
        for j in range(3):
            fns[i][j] = unistr(fns[i][j], myenc)

    if not filelist is None:
        filelist = unescape(filelist)
        fh = Handles()    # only functional for V18 or later.
        # filelist itself is already resolved by the UP because of its parameter type
        filelist = fixloc(unicodeit(filelist), cwd)
        fh.resolvehandles(fns) 

        with codecs.open(filelist, "wb", encoding="utf_8_sig") as f:
            f.writelines([item[0] + ' ' +  item[1] + os.linesep for item in fns])

    spss.StartProcedure("SPSSINC SPLIT DATASET")
    pt = NonProcPivotTable("INFORMATION", tabletitle=_("Split File Information"),
                           columnlabels=[_("Settings and Statistics")])
    pt.addrow(rowlabel=_("Split Variable Names"), cvalues=[", ".join(varnames)])
    pt.addrow(rowlabel=_("Output Directory"), cvalues=[directory])
    pt.addrow(rowlabel=_("Files Deleted"),  cvalues=[str(fnc.delcount)])
    pt.addrow(rowlabel=_("Files Written"),  cvalues=[str(len(fns))])
    pt.addrow(rowlabel=_("File List"),  cvalues=[filelist or _("None")])
    pt.addrow(rowlabel=_("Directories Cleared"), cvalues=[deletecontents and _("Yes") or _("No")])
    pt.generate()

    if printlist:
        pt = NonProcPivotTable("FILEOUTPUT", _("Split Files Written"), 
                               tabletitle=_("Values and File Names for Split Files Written"), 
                               columnlabels=[_("Values or Labels"), _("Directory"), _("Data File")],
                               caption=_("Based on Variables: %s") % ", ".join(varnames))
        for i, f in enumerate(fns):
            row = [f[1]]
            row.extend((os.path.split(f[0].strip('"'))))
            pt.addrow(rowlabel=str(i+1), cvalues=row)
        pt.generate()

    spss.EndProcedure

def unistr(value, myenc):
    """return unicode value for a unicode object, a number, or a code page object"""
    if isinstance(value, unicode):
        return value
    if isinstance(value, (float, int)):
        return unicode(value)
    if value is None:
        return u"$Sysmis"
    return unicode(value, myenc)

def str18(item):
    if v19okay:
        return item


class Strtemplate(object):
    """class for pattern substitution like string.Template but working with arbitrary nonidentifier strings"""
    reexpr = re.compile(r"(\$\{.+?\})")
    def __init__(self, s):
        """s is a string possibly containing patterns of the form ${...}"""

        self.s = s

    def substitute(self, d):
        """substitute all patterns from dictionary d"""

        def repl(mo):
            try:
                return d[mo.group()[2:-1]]
            except:
                raise ValueError(_("A variable reference was found in a directory or file name pattern that is not listed as a split variable: %s") % mo.group()[2:-1])

        return re.sub(Strtemplate.reexpr, repl, self.s)

class filename(object):
    """Generate file names and paths for the split files"""

    def __init__(self, varnames, names, vldict, directory, nameprefix, myenc, unicodeit, 
                 deletecontents, fnspec, filenamesubs):
        """varnames is a sequence of variable names
        names indicates whether value lablels or values are used
        vldict is a sequence of value label dictionaries
        directory is a simple path or a template in which variable values may be substituted
        nameprefix is a prefix for all the file names
        myenc is the character encoding
        deletecontents indicates whether target directories should be cleared of sav files
        fnspec can be used to override the generated file names.  It can be a template.
        filenamesubs can override the names mode."""

        attributesFromDict(locals())
        self.first = True
        if nameprefix and not nameprefix.endswith("_"):
            self.nameprefix = nameprefix + "_"
        self.used = set()
        self.pat = re.compile(r"""[/\\:"*?<>|]""")
        self.dirpat = re.compile(r"""[:"*?<>|]""")
        if not (directory.endswith("/") or directory.endswith("\\")):
            self.directory = self.directory + os.sep
        self.directory = Strtemplate(directory)  # template for split variable substitutions
        self.fnspec = Strtemplate(fnspec)
        self.seq = 0
        self.numvar = len(varnames)
        self.delcount = 0
        if filenamesubs == "asdir":
            self.fnames = names
        else:
            self.fnames = filenamesubs
        self.handles = Handles()

    def genfn(self, values):
        """generate a quoted filespec for values and manage directories

        values is a sequence of one or more values to combine.  It may be a mixture of strings and numbers"""

        nvalues = []
        for v in values:
            if isinstance(v, basestring):
                nvalues.append(v.rstrip())
            elif v is None:
                nvalues.append("$Sysmis")
            else:
                nvalues.append(str(int(v)))
        values = nvalues

        if self.names in ["values", "numbers"]:
            d = dict(zip(self.varnames, values))
            valuelist = ", ".join(values)
        else:
            labels = [self.vldict[i].get(value, value) for i, value in enumerate(values)]
            d = dict(zip(self.varnames, labels))
            valuelist = ", ".join(labels)
        if self.names == self.fnames:   # same substitution mode for directories and filenames
            fd = d
        else:
            if self.fnames in ["values", "numbers"]:
                fd = dict(zip(self.varnames, values))
            else:
                labels = [self.vldict[i].get(value, value) for i, value in enumerate(values)]
                fd = dict(zip(self.varnames, labels))
                
        if self.fnspec.s:
            fn = self.fnspec.substitute(fd)
        else:
            if self.fnames == "labels":
                fn = "_".join([self.vldict[i].get(value, value) for i, value in enumerate(values)])  # use value label if available; else name
            elif self.fnames == "values":
                fn = "_".join(values)
            else:
                self.seq += 1
                fn = "%05d" % self.seq
        if fn is None:
            fn = "$Sysmis"
            value = fn
        fn = unistr(fn, self.myenc)
        ###fnv = unistr(value, self.myenc)
        fnv = fn
        fn = re.sub(self.pat, "_", fn)  # chars illegal in file name (Windows) or at least undesirable on other platforms
        #if fn.lower() in self.used:
            #raise ValueError(_("Output file names are not unique: %s") % fn)
        self.used.add(fn.lower())

        # substitution for illegal characters allows ":" as a drive separator but nowhere else
        actualdir = self.directory.substitute(d)
        # check for file handle and resolve if possible
        if self.handles:
            actualdir = self.handles.resolve(actualdir)
        dirparts = list(os.path.splitdrive(actualdir))  # first item will be empty if no drive letter
        dirparts[-1] = re.sub(self.dirpat, "_", dirparts[-1])
        actualdir = "".join(dirparts)
        if not os.path.isdir(actualdir):    # does directory exist?
            if os.path.isfile(actualdir):      # don't overwrite a file
                raise ValueError("Error: A file exists with the same name as a target directory: %s" % actualdir)
            else:
                os.makedirs(actualdir)
        else:
            if self.deletecontents and self.first:   # 12/8/2011
                self.first = False
                for f in glob.iglob(os.path.join(actualdir, "*.sav")):
                    os.remove(f)
                    self.delcount += 1
        return valuelist, fnv, '"' +  _safeval(os.path.join(actualdir, self.nameprefix  + fn + ".sav")) + '"', self.nameprefix + fn + u".sav"

def makeexpr(varnames, values):
    """Return conditional for this split and value string for output

    varnames is the list of criterion variables
    values is a list of values"""

    crit = []
    for var, value in zip(varnames, values):
        if isinstance(value, basestring):
            expression = var + ' EQ "' + _safeval(value) +'"'
        elif value is None:
            expression = "SYSMIS(%s)" % var
        else:
            expression = var + " EQ " + str(value)
        crit.append(expression)
    return " AND ".join(crit)

def fixloc(filelist, cwd):
    """return filelist aligned with SPSS process

    filelist is a filespec
    cwd is the SPSS process current working directory"""

    if os.path.isabs(filelist):
        return filelist
    parts = os.path.splitdrive(filelist)
    if not parts[0] == "":
        raise ValueError(_("Relative paths cannot be specified with a drive letter: %s") % filelist)
    return os.path.join(cwd, parts[1])

class Handles(object):
    """Version-guarded file handle resolver"""
    def __init__(self):
        try:
            self.fh = spssaux.FileHandles()
        except:
            self.fh = None

    def resolvehandles(self, fns):
        """resolve file handles in spec if V18 or later

        fns is a list where each list element is a list whose first element is the filespec.
        Each filespec actually starts with a double quote"""

        if self.fh:
            for item in fns:
                item[0] = '"' + self.fh.resolve(item[0][1:])

    def resolve(self, filespec):
        "Ordinary handle resolver but guarded.  Returns expanded filespec if possible"

        if self.fh:
            return self.fh.resolve(filespec)
        else:
            return filespec

class NonProcPivotTable(object):
    """Accumulate an object that can be turned into a basic pivot table once a procedure state can be established"""

    def __init__(self, omssubtype, outlinetitle="", tabletitle="", caption="", rowdim="", coldim="", columnlabels=[],
                 procname="Messages"):
        """omssubtype is the OMS table subtype.
        caption is the table caption.
        tabletitle is the table title.
        columnlabels is a sequence of column labels.
        If columnlabels is empty, this is treated as a one-column table, and the rowlabels are used as the values with
        the label column hidden

        procname is the procedure name.  It must not be translated."""

        attributesFromDict(locals())
        self.rowlabels = []
        self.columnvalues = []
        self.rowcount = 0

    def addrow(self, rowlabel=None, cvalues=None):
        """Append a row labelled rowlabel to the table and set value(s) from cvalues.

        rowlabel is a label for the stub.
        cvalues is a sequence of values with the same number of values are there are columns in the table."""

        if cvalues is None:
            cvalues = []
        self.rowcount += 1
        if rowlabel is None:
            self.rowlabels.append(str(self.rowcount))
        else:
            self.rowlabels.append(rowlabel)
        self.columnvalues.extend(cvalues)

    def generate(self):
        """Produce the table assuming that a procedure state is now in effect if it has any rows."""

        privateproc = False
        if self.rowcount > 0:
            try:
                table = spss.BasePivotTable(self.tabletitle, self.omssubtype)
            except:
                spss.StartProcedure(self.procname)
                privateproc = True
                table = spss.BasePivotTable(self.tabletitle, self.omssubtype)
            if self.caption:
                table.Caption(self.caption)
            if self.columnlabels != []:
                table.SimplePivotTable(self.rowdim, self.rowlabels, self.coldim, self.columnlabels, self.columnvalues)
            else:
                table.Append(spss.Dimension.Place.row,"rowdim",hideName=True,hideLabels=True)
                table.Append(spss.Dimension.Place.column,"coldim",hideName=True,hideLabels=True)
                colcat = spss.CellText.String("Message")
                for r in self.rowlabels:
                    cellr = spss.CellText.String(r)
                    table[(cellr, colcat)] = cellr
            if privateproc:
                spss.EndProcedure()

def attributesFromDict(d):
    """build self attributes from a dictionary d."""
    self = d.pop('self')
    for name, value in d.iteritems():
        setattr(self, name, value)

escapemapping = \
              {"\t": r"\t", "\n":r"\n", "\r": r"\r", "\'":r"\'", "\a":r"\a","\b":r"\b", "\f":r"\f","\N":r"\N", "\v":r"\v"}

def unescape(item):
    "repair any escape sequences generated by the UP"
    if item is None:
        return item
    return "".join([escapemapping.get(ch, ch) for ch in item])
