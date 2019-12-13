#--------------------------------------------------------------------------
# File and Version Information:
#  $Id$
#
# Description:
#  Module DdlPsanaDoc...
#
#------------------------------------------------------------------------

"""DDL back-end which generates documentation for PSANA interfaces 

This software was developed for the SIT project.  If you use all or 
part of it, please give an appropriate acknowledgment.

@see DdlPsanaInterfaces

@version $Id$

@author Andy Salnikov
"""
from __future__ import print_function


#------------------------------
#  Module's version from CVS --
#------------------------------
__version__ = "$Revision$"
# $Source$

#--------------------------------
#  Imports of standard modules --
#--------------------------------
import sys
import os
import cgi

#---------------------------------
#  Imports of base class module --
#---------------------------------

#-----------------------------
# Imports for other modules --
#-----------------------------
from psddl.Constant import Constant
from psddl.Package import Package
from psddl.Type import Type
from psddl.Template import Template as T

#----------------------------------
# Local non-exported definitions --
#----------------------------------

_css_file = "psana.css"

_css = """
BODY,H1,H2,H3,H4,H5,H6,P,CENTER,TD,TH,UL,DL,DIV {
    font-family: Geneva, Arial, Helvetica, sans-serif;
}

BODY,TD {
       font-size: 90%;
}
H1 {
    text-align: center;
       font-size: 160%;
}
H2 {
       font-size: 120%;
}
H3 {
       font-size: 100%;
}


A {
       text-decoration: none;
       font-weight: bold;
       color: #000080;
}
A:visited {
       text-decoration: none;
       font-weight: bold;
       color: #000080
}
A:hover {
    text-decoration: none;
    background-color: #E0E0E0;
}

dt { 
margin: 2px;
padding: 2px;
}

.const {font-family:monospace;}
.code {font-family:monospace;}

.methrettype {text-align:right;}

div.def {
background-color: #E0E0E0;
margin: 0px;
padding: 2px;
line-height: 140%;
border: 1px solid #000000;
}

div.descr {
margin: 10px;
padding: 2px;
line-height: 140%;
border: 1px solid #000000;
}

"""

def _typename(type):
    
    return type.fullName('C++')

def _typedecl(type):
    typename = _typename(type)
    if not type.basic : typename = "const "+typename+'&'
    return typename

def _esc(s):
    if type(s) == type({}):
        return dict([(k, _esc(v)) for k, v in s.items()])
    elif type(s) == type(""):
        return cgi.escape(s)
    else:
        return s

#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class DdlPsanaDoc ( object ) :

    @staticmethod
    def backendOptions():
        """ Returns the list of options supported by this backend, returned value is 
        either None or a list of triplets (name, type, description)"""
        return [
            ('psana-inc', 'PATH', "directory for Psana includes, default: psddl_psana"),
            ]


    #----------------
    #  Constructor --
    #----------------
    def __init__ ( self, backend_options, log ) :
        '''Constructor
        
           @param backend_options  dictionary of options passed to backend
           @param log              message logger instance
        '''

        self.dir = backend_options['global:output-dir']
        self.top_pkg = backend_options.get('global:top-package')

        self.psana_inc = backend_options.get('psana-inc', "psddl_psana")

        self._log = log

    #-------------------
    #  Public methods --
    #-------------------

    def packages(self, ns):
        """returns sorted package list"""
        packages = ns.packages()[:]
        packages.sort(key=lambda pkg: pkg.fullName('C++',self.top_pkg))
        return packages

    def types(self, ns):
        """returns sorted types list"""
        types = ns.types()[:]
        types.sort(key=lambda t: t.fullName('C++',self.top_pkg))
        return types

    def methods(self, type):
        """returns sorted methods list"""
        methods = [m for m in type.methods() if m.name != '_sizeof']
        methods.sort(key=lambda t: t.name)
        return methods

    def printPackages(self, ns, out):

        packages = self.packages(ns)
        if packages:
            print('<h2>Packages/namespaces</h2><ul>', file=out)
            for pkg in packages :
                href = _esc(self._pkgFileName(pkg))
                name = _esc(pkg.fullName('C++',self.top_pkg))
                print(T('<li><a href="$href">$name</a></li>')(locals()), file=out)
            print('</ul>', file=out)

    def printTypes(self, ns, out):

        types = self.types(ns)
        if types:
            print('<h2>Types/classes</h2><ul>', file=out)
            for type in types :
                print(T('<li>$ref</li>')(ref=self._typeRef(type)), file=out)
            print('</ul>', file=out)

    def printConstants(self, ns, out):

        constants = ns.constants()[:]
        
        if isinstance(ns, Type):
            if ns.version is not None: 
                comment="XTC type version number"
                c = Constant("Version", ns.version, None, comment=comment)
                constants.insert(0, c)
            if ns.type_id is not None: 
                comment="XTC type ID value (from Pds::TypeId class)"
                c = Constant("TypeId", "Pds::TypeId::"+ns.type_id, None, comment=comment)
                constants.insert(0, c)
        
        if constants:
            print('<h2>Constants</h2>', file=out)
            for const in constants:
                print(T('<div class="descr"><div class="def">$name = $value</div>$comment</div>')\
                        (_esc(const.__dict__)), file=out)


    def printEnum(self, enum, out):
        
        
        print(T('<div class="descr"><div class="def" id="enum_$name">')[enum], file=out)
        print(T('Enumeration <font class="enumname">$name</font>')(name=_esc(enum.fullName('C++',self.top_pkg))), file=out)
        print('</div>', file=out)
        print(T("<p>$comment</p>")(_esc(enum.__dict__)), file=out)
        print("<p>Enumerators:<table>", file=out)
        for const in enum.constants() :
            print('<tr>', file=out)
            val = ""
            if const.value is not None : val = " = " + const.value
            print(T('<td class="const">$name</td>')(_esc(const.__dict__)), file=out)
            print(T('<td class="const">$value</td>')(value=_esc(val)), file=out)
            print(T('<td>$comment</td>')(_esc(const.__dict__)), file=out)
            print('</tr>', file=out)
        print("</table></p>", file=out)
        print('</div>', file=out)

    def printEnums(self, ns, out):

        enums = ns.enums()
        if enums:
            print('<h2>Enumeration types</h2><dl>', file=out)
            for enum in enums:
                self.printEnum(enum, out)
            print('</dl>', file=out)

    def parseTree ( self, model ) :
        
        # open output file
        out = file(os.path.join(self.dir, "index.html"), "w")
        self._htmlHeader(out, "Psana Data Interfaces Reference")
        print('<h1>Psana Data Interfaces Reference</h1>', file=out)
        
        self.printPackages(model, out)

        self.printConstants(model, out)

        self.printEnums(model, out)
        
        self.printTypes(model, out)

        # loop over packages in the model
        for pkg in self.packages(model) :
            self._log.debug("parseTree: package=%s", repr(pkg))
            self._parsePackage(pkg)

        self._htmlFooter(out)
        out.close()
        
        # write CSS
        out = file(os.path.join(self.dir, _css_file), "w")
        out.write(_css)
        out.close()

    def _parsePackage(self, pkg):

        pkgname = pkg.fullName('C++',self.top_pkg)
        filename = self._pkgFileName(pkg)

        # open output file
        out = file(os.path.join(self.dir, filename), "w")
        self._htmlHeader(out, T("Package $name Reference")(name=_esc(pkgname)))
        print(T('<h1>Package $name Reference</h1>')(name=_esc(pkgname)), file=out)

        print(_esc(pkg.comment), file=out)


        self.printPackages(pkg, out)
            
        self.printConstants(pkg, out)

        self.printEnums(pkg, out)
        
        self.printTypes(pkg, out)

        # loop over packages and types
        for type in pkg.types() :
            self._parseType(type)

        self._htmlFooter(out)
        out.close()

    def _parseType(self, type):

        self._log.debug("_parseType: type=%s", repr(type))

        typename = type.fullName('C++',self.top_pkg)
        filename = self._typeFileName(type)

        # open output file
        out = file(os.path.join(self.dir, filename), "w")
        self._htmlHeader(out, T("Class $name Reference")(name=_esc(typename)))
        print(T('<h1>Class $name Reference</h1>')(name=_esc(typename)), file=out)

        if type.location:
            include = os.path.basename(type.location)
            include = os.path.splitext(include)[0] + '.h'
            repourl = T("https://pswww.slac.stanford.edu/trac/psdm/browser/psdm/$package/trunk/include/$header")\
                    (package=self.psana_inc, header=include)
            print(T('<p>Include: <span class="code">#include "<a href="$href">$package/$header</a>"</span></p>')\
                    (href=repourl, package=_esc(self.psana_inc), header=_esc(include)), file=out)

        if type.base:
            print(T("<p>Base class: $base</p>")(base=self._typeRef(type.base)), file=out)

        print(_esc(type.comment), file=out)
            

        self.printConstants(type, out)

        self.printEnums(type, out)
        
        # build the list of all methods
        mlist = []
        for meth in self.methods(type):
            if meth.access == 'public':
                rettype = self._methReturnType(meth)
                args = self._methArgs(meth)
                mlist.append((meth.name, rettype, args, meth.comment))

        # X_shape methods
        for attr in type.attributes():
            if attr.shape_method and attr.accessor and (attr.type.name == 'char' or not attr.type.value_type):
                rettype = "std::vector<int>"
                args = ""
                descr = self._methShapeDescr(attr)
                mlist.append((attr.shape_method, rettype, args, descr))

        
        mlist.sort()
        
        if mlist:
            
            print('<h2>Member Functions</h2>', file=out)
            print('<div class="descr">', file=out)
            print('<table class="methods">', file=out)
            
            for meth in mlist:
                print(self._methDecl(*meth), file=out)
            print('</table></div>', file=out)            

            print('<h2>Member Functions Reference</h2>', file=out)
            
            for meth in mlist:
                print(T('<div class="descr"><div class="def" id="meth_$name">$decl</div>$descr</div>')\
                        (name=meth[0], decl=self._methDecl2(*meth), descr=_esc(meth[3])), file=out)
        

        self._htmlFooter(out)
        out.close()

    def _methDecl(self, name, rettype, args, descr):

        return T('<tr><td class="methrettype">$type</td><td class="methdecl">$name($args)</td></tr>')\
            (type=_esc(rettype), name=self._methRef(_esc(name)), args=_esc(args))

    def _methShapeDescr(self, attr):

        if attr.accessor:
            return """Method which returns the shape (dimensions) of the data returned by 
                %s() method.""" % self._methRef(_esc(attr.accessor.name))
        else:
            return """Method which returns the shape (dimensions) of the data member %s.""" % \
                _esc(attr.name)

    def _methDecl2(self, name, rettype, args, descr):
        return T('$type $name($args)')(type=_esc(rettype), name=_esc(name), args=_esc(args))

    def _methReturnType(self, meth):

        if meth.attribute:
            
            if not meth.attribute.shape:
                
                # attribute is a regular non-array object, 
                # return value or reference depending on what type it is
                typename = _typedecl(meth.attribute.type)

            elif meth.attribute.type.name == 'char':
                
                # char array is actually a string
                typename = "const char*"
                
            elif meth.attribute.type.value_type :
                
                # return ndarray
                typename = T("ndarray<const $type, $rank>")(type=_typename(meth.attribute.type), rank=len(meth.attribute.shape.dims))

            else:

                # array of any other types
                typename = _typedecl(meth.attribute.type)

        elif meth.type is None:
            
            typename = 'void'
            
        else:

            typename = _typedecl(meth.type)
            if meth.rank > 0:
                typename = T("ndarray<const $type, $rank>")(type=typename, rank=meth.rank)
            
        return typename

    def _methArgs(self, meth):

        args = []
        
        if meth.attribute:

            if meth.attribute.shape and not meth.type.basic:
                for i in range(len(meth.attribute.shape.dims)):
                    args.append('uint32_t i%d' % i)

        elif meth.args:
            
            self._log.debug("_methArgs: meth=%s args=%s", meth.name, meth.args)
            for arg in meth.args:
                args.append('%s %s' % (arg[1].name, arg[0]))
            
        return ', '.join(args)

    def _htmlHeader(self, f, title):
        
        print('<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">', file=f)
        print('<html><head><meta http-equiv="Content-Type" content="text/html;charset=iso-8859-1">', file=f)
        print(T('<title>$title</title>')(locals()), file=f)
        print(T('<link href="$href" rel="stylesheet" type="text/css">')(href=_css_file), file=f)
        print('</head><body>', file=f)

    def _htmlFooter(self, f):
        
        print('</body></html>', file=f)

    def _pkgFileName(self, pkg):

        pkgname = pkg.fullName(None,self.top_pkg)
        return "pkg."+pkgname+".html"

    def _typeFileName(self, type):

        typename = type.fullName(None,self.top_pkg)
        return "type."+typename+".html"

    def _pkgRef(self, pkg):

        return self._href(self._pkgFileName(pkg), _esc(pkg.fullName('C++',self.top_pkg)))

    def _typeRef(self, type):

        return self._href(self._typeFileName(type), _esc(type.fullName('C++',self.top_pkg)))

    def _methRef(self, methname):

        return self._href('#meth_'+methname, _esc(methname))

    def _href(self, href, name):

        return T('<a href="$href">$name</a>')(locals())



#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )
