#--------------------------------------------------------------------------
# File and Version Information:
#  $Id$
#
# Description:
#  Module DdlPds2Psana...
#
#------------------------------------------------------------------------

"""DDL parser which generates pds2psana C++ code.

This software was developed for the SIT project.  If you use all or 
part of it, please give an appropriate acknowledgment.

@see RelatedModule

@version $Id$

@author Andrei Salnikov
"""


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
import types

#---------------------------------
#  Imports of base class module --
#---------------------------------

#-----------------------------
# Imports for other modules --
#-----------------------------
from psddl.Attribute import Attribute
from psddl.Enum import Enum
from psddl.Package import Package
from psddl.Type import Type
from psddl.Template import Template as T

#----------------------------------
# Local non-exported definitions --
#----------------------------------

def _interpolate(expr):
    expr = expr.replace('{xtc-config}.', 'cfgPtr->')
    expr = expr.replace('{self}.', "m_xtcObj->")
    return expr

def _dimargs(shape):
    if not shape : return []
    return ', '.join(['uint32_t i%d'%i for i, r in enumerate(shape.dims)])

def _dimexpr(shape):
    return ''.join(['[i%d]'%i for i in range(len(shape.dims))])

def _dimarray(shape):
    return ', '.join([_interpolate(str(s)) for s in shape.dims])

#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class DdlPds2Psana ( object ) :

    #----------------
    #  Constructor --
    #----------------
    def __init__ ( self, incname, cppname, backend_options, log ) :
        """Constructor
        
            @param incname  include file name
        """
        self.incname = incname
        self.cppname = cppname
        self.incdirname = backend_options.get('gen-incdir', "")
        self.top_pkg = backend_options.get('top-package')
        self.psana_inc = backend_options.get('psana-inc', "psddl_psana")
        self.pdsdata_inc = backend_options.get('pdsdata-inc', "psddl_pdsdata")
        self.psana_ns = backend_options.get('psana-ns', "Psana")
        self.pdsdata_ns = backend_options.get('pdsdata-ns', "PsddlPds")

        self._log = log

        #include guard
        g = os.path.split(self.incname)[1]
        if self.top_pkg: g = self.top_pkg + '_' + g
        self.guard = g.replace('.', '_').upper()

    #-------------------
    #  Public methods --
    #-------------------

    def parseTree ( self, model ) :
        
        # open output files
        self.inc = file(self.incname, 'w')
        self.cpp = file(self.cppname, 'w')

        # include guard to header
        print >>self.inc, "#ifndef", self.guard 
        print >>self.inc, "#define", self.guard, "1"

        msg = "\n// *** Do not edit this file, it is auto-generated ***\n"
        print >>self.inc, msg
        print >>self.cpp, msg

        print >>self.inc, "#include <vector>"
        print >>self.inc, "#include <boost/shared_ptr.hpp>"

        inc = os.path.join(self.incdirname, os.path.basename(self.incname))
        print >>self.cpp, T("#include \"$inc\"\n")(locals())
        print >>self.cpp, "#include <cstddef>\n"
        print >>self.cpp, "#include <stdexcept>\n"

        # headers for psana and pdsdata includes
        inc = os.path.join(self.psana_inc, os.path.basename(self.incname))
        print >>self.inc, T("#include \"$inc\"")(locals())
        inc = os.path.join(self.pdsdata_inc, os.path.basename(self.incname))
        print >>self.inc, T("#include \"$inc\"")(locals())

        # headers for other included packages
        for use in model.use:
            path = use['file']
            headers = use['cpp_headers']
            if not headers:
                header = os.path.splitext(path)[0] + '.h'
                header = os.path.join(self.incdirname, os.path.basename(header))
                headers = [header]
            for header in headers:
                print >>self.inc, T("#include \"$header\"")(locals())

        if self.top_pkg : 
            print >>self.inc, T("namespace $top_pkg {")[self]
            print >>self.cpp, T("namespace $top_pkg {")[self]

        # loop over packages in the model
        for pkg in model.packages() :
            if not pkg.included :
                self._log.debug("parseTree: package=%s", repr(pkg))
                self._parsePackage(pkg)

        if self.top_pkg : 
            print >>self.inc, T("} // namespace $top_pkg")[self]
            print >>self.cpp, T("} // namespace $top_pkg")[self]

        # close include guard
        print >>self.inc, "#endif //", self.guard

        # close all files
        self.inc.close()
        self.cpp.close()


    def _parsePackage(self, pkg):

        # open namespaces
        print >>self.inc, T("namespace $name {")[pkg]
        print >>self.cpp, T("namespace $name {")[pkg]

        # regular enums
        for enum in pkg.enums() :
            if not enum.included :
                self._genEnum(enum)

        # loop over packages and types
        for ns in pkg.namespaces() :
            
            if isinstance(ns, Package) :
                
                self._parsePackage(ns)
            
            elif isinstance(ns, Type) :
    
                self._parseType(type = ns)

        # close namespaces
        print >>self.inc, T("} // namespace $name")[pkg]
        print >>self.cpp, T("} // namespace $name")[pkg]

    def _genEnum(self, enum):

        self._log.debug("_genEnum: type=%s", repr(enum))

        if not enum.name: return

        pdstype = enum.fullName('C++', self.pdsdata_ns)
        psanatype = enum.fullName('C++', self.psana_ns)
        
        print >>self.cpp, T("$psanatype pds_to_psana($pdstype e)\n{\n  return $psanatype(e);\n}\n")(locals())


    def _parseType(self, type):

        self._log.debug("_parseType: type=%s", repr(type))

        # skip included types
        if type.included : return

        # regular enums
        for enum in type.enums() :
            self._genEnum(enum)

        if not type.value_type :
            
            self._genAbsType(type)
            
        else:
            
            self._genValueType(type)


    def _genValueType(self, type):

        self._log.debug("_genValueType: type=%s", repr(type))

        typename = type.fullName('C++')

        # need to call a non-default constructor on a type
        ctor = None
        for c in type.ctors:
            if c.args or 'auto' in c.tags:
                if ctor:
                    self._log.warning('Constructor overload for %s, using first constructor', typename)
                else:
                    ctor = c

        if not ctor : 
            self._log.warning('No suitable constructor defined for %s', typename)
            return

        self._log.debug("_genValueType: ctor args=%s", repr(ctor.args))
        
        ctor_args = []
        for arg in ctor.args:

            atype = arg.type

            if not arg.dest.accessor:
                raise ValueError('attribute %s has no access method' % arg.dest.name)

            expr = "pds."+arg.method.name+"()"
            if isinstance(arg.dest, Attribute) and arg.dest.shape:
                if atype.name == 'char':
                    # accessor returns char* and takes few indices
                    idx = ','.join(['0']*(len(arg.dest.shape.dims)-1))
                    expr = "pds."+arg.method.name+"("+idx+")"
                elif atype.value_type:
                    # accessor returns ndarray, we need pointer
                    expr = "pds."+arg.method.name+"().data()"
                
            if not atype.basic and not atype.external or isinstance(atype, Enum):
                expr = T("pds_to_psana($expr)")(expr=expr)
            ctor_args.append(expr)

        ctor_args = ', '.join(ctor_args)


        print >>self.inc, T("$psana_ns::$typename pds_to_psana($pdsdata_ns::$typename pds);\n")\
            (self.__dict__, typename=typename)

        print >>self.cpp, T("$psana_ns::$typename pds_to_psana($pdsdata_ns::$typename pds)\n{")\
            (self.__dict__, typename=typename)
        print >>self.cpp, T("  return $psana_ns::$typename($ctor_args);")\
            (locals(), psana_ns=self.psana_ns)
        print >>self.cpp, "}\n"
        

    def _genAbsType(self, type):
        
        def _types(type):
            """Generator for the type list of the given type plus all it bases"""
            if type.base:
                for t in _types(type.base): yield t
            yield type
        
        self._log.debug("_genAbsType: type=%s", repr(type))

        pdstypename = type.fullName('C++', self.pdsdata_ns)
        psanatypename = type.fullName('C++', self.psana_ns)

        print >>self.inc, ""
        if type.xtcConfig: print >>self.inc, "template <typename Config>"
        print >>self.inc, T("class $name : public $psanatype {\npublic:")(name=type.name, psanatype=psanatypename)

        print >>self.inc, T("  typedef $pdstypename XtcType;")(locals())
        print >>self.inc, T("  typedef $psanatypename PsanaType;")(locals())
        
        self._genCtor(type)
        
        print >>self.inc, T("  virtual ~$name();")[type]
        if type.xtcConfig:
            print >>self.cpp, "template <typename Config>"
            print >>self.cpp, T("$name<Config>::~$name()\n{\n}\n")[type]
        else:
            print >>self.cpp, T("$name::~$name()\n{\n}\n")[type]

        # declarations for public methods 
        for t in _types(type):
            for meth in t.methods(): 
                if meth.access == 'public': self._genMethod(meth, type)

        # generate _shape() methods for array attributes
        for t in _types(type):
            for attr in t.attributes() :
                self._genAttrShapeDecl(attr, type)

        print >>self.inc, "  const XtcType& _xtcObj() const { return *m_xtcObj; }"

        print >>self.inc, "private:"

        print >>self.inc, "  boost::shared_ptr<const XtcType> m_xtcObj;"
        
        # declaration for config pointer
        if type.xtcConfig: 
            print >>self.inc, "  boost::shared_ptr<const Config> m_cfgPtr;"
        
        # declarations for data members
        for attr in type.attributes() :
            self._genAttrDecl(attr)

        # close class declaration
        print >>self.inc, "};\n"

        for cfg in type.xtcConfig:
            print >>self.cpp, T("template class $name<$config>;")(name=type.name, config=cfg.fullName('C++', self.pdsdata_ns))

    def _genMethod(self, meth, type):
        """Generate method declaration and definition"""

        self._log.debug("_genMethod: meth: %s", meth)
        
        if meth.attribute:
            
            # generate access method for a named attribute
            
            attr = meth.attribute

            if attr.type.basic:
                
                cfgNeeded = False
                cvt = False
                shptr = False
                if '{xtc-config}' in str(attr.offset) : cfgNeeded = True
                if attr.type is not attr.stor_type: cvt = True

                args = []
                rettype = attr.type.fullName('C++', self.psana_ns)
                if attr.shape :
                    for d in attr.shape.dims:
                        if '{xtc-config}' in str(d) : cfgNeeded = True
                    if attr.type.name == 'char':
                        rettype = "const char*"
                        args = [('i%d'%i, type.lookup('uint32_t')) for i in range(len(attr.shape.dims)-1)]
                    else:
                        rettype = attr.stor_type.fullName('C++', self.psana_ns)
                        cvt = False
                        shptr = True
                        rettype = T("ndarray<const $type, $rank>")(type=rettype, rank=len(attr.shape.dims))
                self._genFwdMeth(meth.name, rettype, type, cfgNeeded, cvt, args=args, shptr=shptr)
            
            else:

                psana_type = attr.type.fullName('C++', self.psana_ns)
                classname = type.name
                if type.xtcConfig:
                    classname += '<Config>'
                    print >>self.cpp, 'template <typename Config>'

                if not attr.shape:
                    
                    # attribute is a regular non-array object
                    print >>self.inc, T("  virtual const $type& $name() const;")(type=psana_type, name=meth.name)
                    print >>self.cpp, T("const $type& $classname::$name() const { return $attr; }")\
                            (type=psana_type, classname=classname, name=meth.name, attr=attr.name)
                        
                elif attr.type.value_type:
                    
                    # attribute is an array accessed through ndarray
                    ndarray = T("ndarray<const $type, $rank>")(type=psana_type, rank=len(attr.shape.dims))
                    print >>self.inc, T("  virtual $type $name() const;")(type=ndarray, name=meth.name)
                    expr = T("${name}_ndarray_storage_")(name=attr.name)
                    print >>self.cpp, T("$type $classname::$name() const { return $expr; }")\
                            (type=ndarray, classname=classname, name=meth.name, expr=expr)
                        
                else:
    
                    # attribute is an array object, return pointer for basic types,
                    # or reference to elements for composite types
                    expr = attr.name + _dimexpr(attr.shape)
                    print >>self.inc, T("  virtual const $type& $meth($args) const;")\
                            (type=psana_type, meth=meth.name, args=_dimargs(attr.shape))
                    print >>self.cpp, T("const $type& $classname::$meth($args) const { return $expr; }")\
                            (type=psana_type, classname=classname, meth=meth.name, args=_dimargs(attr.shape), expr=expr)

        else:

            # explicitly declared method with optional expression
            
            if meth.name == "_sizeof" : return
            
            # check if config object is needed
            body = meth.code.get("C++")
            if not body : body = meth.code.get("Any")
            if not body :
                expr = meth.expr.get("C++")
                if not expr : expr = meth.expr.get("Any")
                if expr:
                    body = expr
                    if type: body = T("return $expr;")(locals())
            cfgNeeded = False
            if body:
                cfgNeeded = body.find('{xtc-config}') >= 0

            # if no type given then it does not return anything
            rettype = meth.type
            cvt = False
            if rettype is None:
                rettype = "void"
            elif rettype.basic and not isinstance(rettype, Enum):
                rettype = rettype.fullName('C++')
                if meth.rank > 0:
                    rettype = T("ndarray<const $type, $rank>")(type=rettype, rank=meth.rank)
            else:
                cvt = True
                rettype = rettype.fullName('C++', self.psana_ns)

            self._genFwdMeth(meth.name, rettype, type, cfgNeeded, cvt, meth.args)

    def _genFwdMeth(self, name, typedecl, type, cfgNeeded=False, cvt=False, args=None, shptr=False):
        args = args or []
        
        argdecl = ['%s %s' % (atype.fullName('C++'), aname) for aname, atype in args]
        argdecl = ', '.join(argdecl)
        
        passargs = [aname for aname, atype in args]
        passargs = ', '.join(passargs)
        
        print >>self.inc, T("  virtual $type $meth($args) const;")(type=typedecl, meth=name, args=argdecl)
        print >>self.cpp, ""
        cfg = ''
        Class = type.name
        if type.xtcConfig: 
            Class += '<Config>'
            print >>self.cpp, "template <typename Config>"
        print >>self.cpp, T("$type $Class::$meth($args) const {")(type=typedecl, Class=Class, meth=name, args=argdecl)
        
        if cfgNeeded :
            if passargs: 
                passargs = '*m_cfgPtr, '+passargs
            else:
                passargs = '*m_cfgPtr'
        if shptr:
            if passargs: 
                passargs += ', m_xtcObj'
            else:
                passargs = 'm_xtcObj'
        expr = T("m_xtcObj->$meth($passargs)")(meth=name, passargs=passargs)
        if cvt: expr = 'pds_to_psana({0})'.format(expr)
        print >>self.cpp, T("  return $expr;")(expr=expr)
        print >>self.cpp, "}\n"

    def _genAttrDecl(self, attr):
        
        # basic types do not need conversion
        if attr.type.basic: return
        
        # need corresponding psana type
        if attr.type.value_type:
            psana_type =  attr.type.fullName('C++', self.psana_ns)
        else :
            psana_type = attr.type.fullName('C++', self.top_pkg)
            if attr.type.xtcConfig: psana_type += '<Config>'

        if not attr.shape:
            
            print >>self.inc, T("  $type $attr;")(type=psana_type, attr=attr.name)

        elif attr.type.value_type:
            
            # for value types we return ndarray which needs contiguous memory
            print >>self.inc, T("  ndarray<$type, $rank> ${attr}_ndarray_storage_;")(type=psana_type, attr=attr.name, rank=len(attr.shape.dims))

        else :

            atype = psana_type
            for d in attr.shape.dims:
                atype = "std::vector< %s >" % atype
            print >>self.inc, T("  $type $attr;")(type=atype, attr=attr.name)


    def _genCtor(self, type):

        self._log.debug("_genCtor: type: %s", type)

        args = "const boost::shared_ptr<const XtcType>& xtcPtr"
        if type.xtcConfig:
            args += ", const boost::shared_ptr<const Config>& cfgPtr"
        if type.size.value is None:
            # special case when the data size have to be guessed from XTC size
            args += ", size_t xtcSize"
            
        print >>self.inc, T("  $Class($args);")(Class=type.name, args=args)
        
        if type.size.value is not None:
            
            # if size is None manual implementation of the constructor will be provided
            
            if type.xtcConfig:
                print >>self.cpp, "template <typename Config>"
                print >>self.cpp, T("$Class<Config>::$Class($args)")(Class=type.name, args=args)
            else:
                print >>self.cpp, T("$Class::$Class($args)")(Class=type.name, args=args)
            print >>self.cpp, T("  : $base()")(base=type.fullName('C++', self.psana_ns))
            print >>self.cpp, "  , m_xtcObj(xtcPtr)"
            if type.xtcConfig: print >>self.cpp, "  , m_cfgPtr(cfgPtr)"
            
            # member initialization
            for attr in type.attributes() :
                self._genAttrInitNonArray(attr)
            
            print >>self.cpp, "{"
    
            # member initialization
            for attr in type.attributes() :
                self._genAttrInitArray(attr)
                
            print >>self.cpp, "}"


    def _genAttrInitNonArray(self, attr):

        # all basic types are forwarded to xtc 
        if attr.type.basic: return
        
        # arrays are initialized inside constructor
        if attr.shape: return

        # how to get access to member
        if attr.access == 'public' :
            expr = T("xtcPtr->$name")[attr]
        elif attr.accessor is not None:
            expr = T("xtcPtr->$name()")[attr.accessor]

        # may need to mangle name
        name = attr.name

        if attr.type.external:
            print >>self.cpp, T("  , $name($expr)")(locals())
        elif attr.type.value_type:
            ns = attr.type.parent.fullName('C++', self.top_pkg)
            print >>self.cpp, T("  , $name($ns::pds_to_psana($expr))")(locals())
        else :
            xtc_type = attr.type.fullName('C++', self.pdsdata_ns)
            print >>self.cpp, T("  , $name(boost::shared_ptr<const $xtc_type>(xtcPtr, &$expr))")(locals())


    def _genAttrInitArray(self, attr):

        def subscr(r):
            return "".join(['[i%d]'%i for i in range(r)])
        def subscr_comma(r):
            return ",".join(['i%d'%i for i in range(r)])

        # all basic types are forwarded to xtc 
        if attr.type.basic: return
        
        if not attr.shape: return

        # may need to mangle name
        name = attr.name

        ndims = len(attr.shape.dims)

        # for value types we do ndarrays in separate method
        if attr.type.value_type: 
            return self._genAttrInitNDArray(attr)

        # config objects may be needed
        cfgNeeded = False
        if str(attr.offset).find('{xtc-config}') >= 0:
            cfgNeeded = True
        if str(attr.type.size).find('{xtc-config}') >= 0:
            cfgNeeded = True

        print >>self.cpp, "  {"
        
        cfg = ''
        for d in attr.shape.dims:
            if '{xtc-config}' in str(d) : cfg = "*cfgPtr"
        print >>self.cpp, T("    const std::vector<int>& dims = xtcPtr->$meth($cfg);")(meth=attr.shape_method, cfg=cfg)

        for r in range(ndims):
            idx = 'i%d'%r
            offset = "  "*(r+1)
            print >>self.cpp, offset+T("  $name$subscr.reserve(dims[$dim]);")(name=name, subscr=subscr(r), dim=r)
            print >>self.cpp, offset+T("  for (int $i=0; $i != dims[$dim]; ++$i) {")(i=idx, dim=r) 
            if r != ndims-1:
                print >>self.cpp, offset+T("    $name$subscr.resize(dims[$dim]);")(name=name, subscr=subscr(r), dim=r)
            else:
                # how to get access to member
                if attr.access == 'public' :
                    expr = T("xtcPtr->$attr$subscr")(attr=attr.name, subscr=subscr(r+1))
                elif attr.accessor is not None:
                    if cfgNeeded:
                        expr = T("xtcPtr->$meth(*cfgPtr, $subscr)")(meth=attr.accessor.name, subscr=subscr_comma(r+1))
                    else:
                        expr = T("xtcPtr->$meth($subscr)")(meth=attr.accessor.name, subscr=subscr_comma(r+1))
                if attr.type.external:
                    pass
                elif attr.type.value_type:
                    ns = attr.type.parent.fullName('C++', self.top_pkg)
                    expr = T("$ns::pds_to_psana($expr)")(locals())
                else:
                    attrXtcType = attr.type.fullName('C++', self.pdsdata_ns)
                    print >>self.cpp, offset+T("    const $type& d = $expr;")(type=attrXtcType, expr=expr)
                    print >>self.cpp, offset+T("    boost::shared_ptr<const $type> dPtr(m_xtcObj, &d);")(type=attrXtcType)
                    expr = "dPtr"
                    typename = attr.type.fullName('C++', self.top_pkg)
                    if attr.type.xtcConfig: 
                        expr += ", cfgPtr"
                        typename += '<Config>'
                    expr = T("$type($expr)")(type=typename, expr=expr)
                print >>self.cpp, offset+T("    $name$subscr.push_back($expr);")(name=name, subscr=subscr(r), expr=expr)

        for r in range(ndims):
            offset = "  "*(ndims-r)
            print >>self.cpp, offset+"  }" 

        print >>self.cpp, "  }" 

    def _genAttrInitNDArray(self, attr):

        pdstypename = attr.type.fullName('C++', self.pdsdata_ns)
        psanatypename = attr.type.fullName('C++', self.psana_ns)

        # may need to mangle name
        name = attr.name

        ndims = len(attr.shape.dims)

        cfgNeeded = False
        if str(attr.offset).find('{xtc-config}') >= 0:
            cfgNeeded = True
        for d in attr.shape.dims:
            if '{xtc-config}' in str(d) : cfgNeeded = True
            
        cfg = ""
        if cfgNeeded: cfg = "*cfgPtr"
        
        if attr.type.external:
            elem_expr = '*it'
        else:
            ns = attr.type.parent.fullName('C++', self.top_pkg)
            elem_expr = T('$ns::pds_to_psana(*it)')(locals())
            
        # ndarray initialization
        print >>self.cpp, "  {"
        print >>self.cpp, T("    typedef ndarray<$type, $rank> NDArray;")(type=psanatypename, rank=ndims)
        print >>self.cpp, T("    typedef ndarray<const $type, $rank> XtcNDArray;")(type=pdstypename, rank=ndims)
        print >>self.cpp, T("    const XtcNDArray& xtc_ndarr = xtcPtr->$meth($cfg);")(meth=attr.accessor.name, cfg=cfg)
        print >>self.cpp, T("    ${name}_ndarray_storage_ = NDArray(xtc_ndarr.shape());")(locals())
        print >>self.cpp, T("    NDArray::iterator out = ${name}_ndarray_storage_.begin();")(locals())
        print >>self.cpp, "    for (XtcNDArray::iterator it = xtc_ndarr.begin(); it != xtc_ndarr.end(); ++ it, ++ out) {"
        print >>self.cpp, T("      *out = $elem_expr;")(locals())
        print >>self.cpp, "    }"
        print >>self.cpp, "  }" 


    def _genAttrShapeDecl(self, attr, type):

        if not attr.shape_method: return 
        if not attr.accessor: return
        
        # value-type arrays return ndarrays which do not need shape method
        if attr.type.value_type and attr.type.name != 'char': return

        if attr.type.basic:

            cfgNeeded = False
            if attr.shape:
                for d in attr.shape.dims:
                    if '{xtc-config}' in str(d) : cfgNeeded = True
            self._genFwdMeth(attr.shape_method, "std::vector<int>", type, cfgNeeded)
            
        else:

            # may need to mangle name
            name = attr.name
            if attr.access == 'public' : name += "_pub_member_"

            shape = attr.shape.dims

            print >>self.inc, T("  virtual std::vector<int> $meth() const;")(meth=attr.shape_method)
            
            Class = type.name
            if type.xtcConfig: 
                Class += '<Config>'
                print >>self.cpp, 'template <typename Config>'
            print >>self.cpp, T("std::vector<int> $Class::$meth() const\n{")(Class=Class, meth=attr.shape_method)
            print >>self.cpp, "  std::vector<int> shape;" 
            print >>self.cpp, T("  shape.reserve($rank);")(rank=len(shape))
            v = name
            for s in shape:
                print >>self.cpp, T("  shape.push_back($attr.size());")(attr=v)
                v += '[0]'
            print >>self.cpp, "  return shape;\n}\n"


#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )
