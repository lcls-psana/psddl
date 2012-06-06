#--------------------------------------------------------------------------
# File and Version Information:
#  $Id: PythonCodegen.py 3615 2012-05-22 17:50:05Z jbarrera@SLAC.STANFORD.EDU $
#
# Description:
#  Module PythonCodegen...
#
#------------------------------------------------------------------------

"""Calss responsible for C++ code generation for Type object 

This software was developed for the SIT project.  If you use all or 
part of it, please give an appropriate acknowledgment.

@see RelatedModule

@version $Id: PythonCodegen.py 3615 2012-05-22 17:50:05Z jbarrera@SLAC.STANFORD.EDU $

@author Andrei Salnikov
"""


#------------------------------
#  Module's version from CVS --
#------------------------------
__version__ = "$Revision: 3615 $"
# $Source$

#--------------------------------
#  Imports of standard modules --
#--------------------------------
import sys
import logging
import re

#---------------------------------
#  Imports of base class module --
#---------------------------------

#-----------------------------
# Imports for other modules --
#-----------------------------
from psddl.Attribute import Attribute
from psddl.ExprVal import ExprVal
from psddl.Method import Method
from psddl.Type import Type
from psddl.Template import Template as T

#----------------------------------
# Local non-exported definitions --
#----------------------------------

def _interpolate(expr, typeobj):
    
    expr = expr.replace('{xtc-config}', 'cfg')
    expr = expr.replace('{type}.', typeobj.name+"::")
    expr = expr.replace('{self}.', "this->")
    return expr

def _typename(type):
    
    return type.fullName('C++')

def _typedecl(type):
    typename = _typename(type)
    if not type.basic : typename = "const "+typename+'&'
    return typename

def _argdecl(name, type):    
    return _typedecl(type) + ' ' + name

def _argdecl2(name, type):    
    return name

def _dims(dims):
    return ''.join(['[%s]'%d for d in dims])

def _dimargs(dims, type):
    int_type = type.lookup('uint32_t')
    return [('i%d'%i, int_type) for i in range(len(dims))]

def _dimexpr(dims):
    return ''.join(['[i%d]'%i for i in range(len(dims))])

#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class PythonCodegen ( object ) :

    #----------------
    #  Constructor --
    #----------------
    def __init__ ( self, inc, cpp, type, abstract=False, namespace_prefix="" ) :

        # define instance variables
        self._inc = inc
        self._cpp = cpp
        self._type = type
        self._abs = abstract
        self._pywrapper = True
        self._namespace_prefix = namespace_prefix

    #-------------------
    #  Public methods --
    #-------------------

    def codegen(self):

        logging.debug("PythonCodegen.codegen: type=%s", repr(self._type))

        # class-level comment
        print >>self._inc, T("\n/** @class $name\n\n  $comment\n*/\n")[self._type]

        # declare config classes if needed
        for cfg in self._type.xtcConfig:
            print >>self._inc, T("class $name;")[cfg]

        # for non-abstract types C++ may need pack pragma
        needPragmaPack = not self._abs and self._type.pack
        if needPragmaPack : 
            print >>self._inc, T("#pragma pack(push,$pack)")[self._type]

        # base class
        base = ""
        if self._type.base and not self._pywrapper : base = T(": public $name")[self._type.base]

        # this class (class being generated)
        name = self._type.name
        if self._pywrapper:
            wrapped = name
            name = wrapped + "_Wrapper"

        # start class declaration
        print >>self._inc, T("\nclass $name$base {")(name = name, base = base)
        access = "private"

        if self._pywrapper:
            # shared_ptr and C++ pointer to wrapped object
            print >>self._inc, T("  boost::shared_ptr<$wrapped> _o;")(wrapped = wrapped)
            print >>self._inc, T("  $wrapped* o;")(wrapped = wrapped)

        # enums for version and typeId
        access = self._access("public", access)
        if self._type.type_id is not None: 
            doc = '/**< XTC type ID value (from Pds::TypeId class) */'
            print >>self._inc, T("  enum { TypeId = Pds::TypeId::$type_id $doc };")(type_id=self._type.type_id, doc=doc)
        if self._type.version is not None: 
            doc = '/**< XTC type version number */'
            print >>self._inc, T("  enum { Version = $version $doc };")(version=self._type.version, doc=doc)

        # enums for constants
        access = self._access("public", access)
        for const in self._type.constants() :
            self._genConst(const)

        # regular enums
        access = self._access("public", access)
        for enum in self._type.enums() :
            self._genEnum(enum)

        # constructors and destructors
        if self._pywrapper:
            # constructor
            access = self._access("public", access)
            #print >>self._inc, T("  $name(boost::shared_ptr<$wrapped> obj) : _o(obj), o(_o.get()) {}")(name = name, wrapped = wrapped)
            #print >>self._inc, T("  $name($wrapped* obj) : o(obj) {}")(name = name, wrapped = wrapped)
            #print >>self._cpp, T("\n#define _CLASS(n, policy) class_<n>(\"${prefix}${wrapped}\", no_init)\\")(prefix = self._namespace_prefix, wrapped = wrapped)


            print >>self._inc, T("  $name(boost::shared_ptr<$wrapped> obj) : _o(obj), o(_o.get()) {}")(locals())
            print >>self._inc, T("  $name($wrapped* obj) : o(obj) {}")(locals())
            print >>self._cpp, T("\n#define _CLASS(n, policy) class_<n>(#n, no_init)\\")(locals())

        else:
            if not self._abs:
                # constructor, all should be declared explicitly
                for ctor in self._type.ctors :
                    access = self._access(ctor.access, access)
                    self._genCtor(ctor)
            if self._abs:
                # need virtual destructor
                access = self._access("public", access)
                print >>self._inc, T("  virtual ~$name();")[self._type]
                print >>self._cpp, T("\n$name::~$name() {}\n")[self._type]

        # generate methods (for interfaces public methods only)
        for meth in self._type.methods(): 
            access = self._access("public", access)
            if not self._abs or meth.access == "public": self._genMethod(meth)

        # generate _shape() methods for array attributes
        for attr in self._type.attributes() :
            access = self._access("public", access)
            self._genAttrShapeDecl(attr)

        if not self._abs:
            # data members
            for attr in self._type.attributes() :
                access = self._access("private", access)
                self._genAttrDecl(attr)

        # close class declaration
        print >>self._inc, "};"
        if self._pywrapper:
            prefix = self._namespace_prefix
            print >>self._cpp, ""
            if not self._abs:
                print >>self._cpp, T('  _CLASS($prefix$wrapped, return_value_policy<copy_const_reference>());')(locals())
            print >>self._cpp, T('  _CLASS($prefix$name, return_value_policy<return_by_value>());')(locals())
            if not self._abs:
                print >>self._cpp, T('  std_vector_class_($wrapped);')(locals())
            print >>self._cpp, T('  std_vector_class_($name);')(locals())
            print >>self._cpp, '#undef _CLASS';
            if re.match(r'.*(Data|DataDesc|Config)V[1-9][0-9]*_Wrapper', name):
                print >>self._cpp, T('  ADD_GETTER($wrapped);')(locals())
            print >>self._cpp, ""

        # close pragma pack
        if needPragmaPack : 
            print >>self._inc, "#pragma pack(pop)"

    def _access(self, newaccess, oldaccess):
        if newaccess != oldaccess:
            print >>self._inc, newaccess+":"
        return newaccess
        
    def _genConst(self, const):
        
        doc = ""
        if const.comment: doc = T("/**< $comment */ ")[const]
        print >>self._inc, T("  enum { $name = $value $doc};")(name=const.name, value=const.value, doc=doc)

    def _genEnum(self, enum):
        
        if enum.comment: print >>self._inc, T("\n  /** $comment */")[enum]
        print >>self._inc, T("  enum $name {")(name = enum.name or "")
        for const in enum.constants() :
            val = ""
            if const.value is not None : val = " = " + const.value
            doc = ""
            if const.comment: doc = T(' /**< $comment */')[const]
            print >>self._inc, T("    $name$value,$doc")(name=const.name, value=val, doc=doc)
        print >>self._inc, "  };"

    def _genAttrDecl(self, attr):
        """Generate attribute declaration"""
        
        logging.debug("_genAttrDecl: attr: %s", attr)
        
        doc = ""
        if attr.comment : doc = T("\t/**< $comment */")(comment = attr.comment.strip())
        
        if not attr.shape :
            if attr.isfixed():
                decl = T("  $type\t$name;$doc")(type=_typename(attr.type), name=attr.name, doc=doc)
            else:
                decl = T("  //$type\t$name;")(type=_typename(attr.type), name=attr.name)
        else:
            if attr.isfixed():
                dim = _interpolate(_dims(attr.shape.dims), attr.parent)
                decl = T("  $type\t$name$shape;$doc")(type=_typename(attr.type), name=attr.name, shape=dim, doc=doc)
            else :
                dim = _interpolate(_dims(attr.shape.dims), attr.parent)
                decl = T("  //$type\t$name$shape;")(type=_typename(attr.type), name=attr.name, shape=dim)
        print >>self._inc, decl


    def _genMethod(self, meth):
        """Generate method declaration and definition"""

        logging.debug("_genMethod: meth: %s", meth)
        
        if meth.attribute:
            
            # generate access method for a named attribute
            
            attr = meth.attribute
            args = []
                        
            if not attr.shape:
                
                # attribute is a regular non-array object, 
                # return value or reference depending on what type it is
                rettype = _typedecl(attr.type)
                body = self._bodyNonArray(attr)

            elif attr.type.name == 'char':
                
                # char array is actually a string
                rettype = "const char*"
                args = _dimargs(attr.shape.dims[:-1], self._type)
                body = self._bodyCharArrray(attr)
                
            elif attr.type.value_type :
                
                # return ndarray
                rettype = "ndarray<%s, %d>" % (_typename(attr.type), len(attr.shape.dims))
                body = self._bodyNDArrray(attr)

            else:

                # array of any other types
                rettype = _typedecl(attr.type)
                args = _dimargs(attr.shape.dims, self._type)
                body = self._bodyAnyArrray(attr)


            # guess if we need to pass cfg object to method
            cfgNeeded = body.find('{xtc-config}') >= 0
            body = _interpolate(body, self._type)

            configs = [None]
            if cfgNeeded and not self._abs: configs = attr.parent.xtcConfig
            for cfg in configs:

                cargs = []
                if cfg: cargs = [('cfg', cfg)]

                self._genMethodBody(meth.name, rettype, body, cargs + args, inline=True, doc=attr.comment)

        elif meth.bitfield:

            # generate access method for bitfield

            bf = meth.bitfield
            expr = bf.expr()
            cfgNeeded = expr.find('{xtc-config}') >= 0
            expr = _interpolate(expr, meth.parent)

            configs = [None]
            if cfgNeeded and not self._abs: configs = meth.parent.xtcConfig
            for cfg in configs:

                args = []
                if cfg: args = [('cfg', cfg)]

                self._genMethodExpr(meth.name, _typename(meth.type), expr, args, inline=True, doc=meth.comment)

        else:

            # explicitly declared method with optional expression
            
            if meth.name == "_sizeof" and self._abs : return
            
            # if no type given then it does not return anything
            type = meth.type
            if type is None:
                type = "void"
            else:
                type = _typename(type)
                if meth.rank > 0:
                    type = "ndarray<%s, %d>" % (type, meth.rank)

            # make method body
            body = meth.code.get("C++")
            if not body : body = meth.code.get("Any")
            if not body :
                expr = meth.expr.get("C++")
                if not expr : expr = meth.expr.get("Any")
                if expr:
                    body = expr
                    if type: body = "return %s;" % expr
                
            # config objects may be needed 
            cfgNeeded = False
            if body: 
                cfgNeeded = body.find('{xtc-config}') >= 0
                body = _interpolate(body, meth.parent)

            # default is not inline, can change with a tag
            inline = 'inline' in meth.tags
            
            configs = [None]
            if cfgNeeded and not self._abs: configs = meth.parent.xtcConfig
            for cfg in configs:

                args = []
                if cfg: args = [('cfg', cfg)]
                args += meth.args

                self._genMethodBody(meth.name, type, body, args, inline, static=meth.static, doc=meth.comment)


    def _bodyNonArray(self, attr):
        """Makes method body for methods returning non-array attribute values"""

        if attr.isfixed():

            return T("return $name;")[attr]
        
        else:
            
            body = T("ptrdiff_t offset=$offset;")[attr]
            body += T("\n  return *(const $type*)(((const char*)this)+offset);")(type=_typename(attr.type))
            return body

    def _bodyCharArrray(self, attr):
        """Makes method body for methods returning char*"""

        if attr.isfixed():

            return T("return $name$dimexpr;")(name=attr.name, dimexpr=_dimexpr(attr.shape.dims[:-1]))
        
        else:
            
            body = T("typedef char atype$dims;")(dims=_dims(attr.shape.dims[1:]))
            body += T("\n  ptrdiff_t offset=$offset;")[attr]
            body += "\n  const atype* pchar = (const atype*)(((const char*)this)+offset);"
            body += T("\n  return pchar$dimexpr;")(dimexpr=_dimexpr(attr.shape.dims[:-1]))
            return body

    def _bodyNDArrray(self, attr):
        """Makes method body for methods returning ndarray"""

        shape = ', '.join([str(s or 0) for s in attr.shape.dims])
        if attr.isfixed():

            idx0 = "[0]" * len(attr.shape.dims)
            return T("return make_ndarray(&$name$idx, $shape);")(name=attr.name, idx=idx0, shape=shape)

        else:
            
            body = T("ptrdiff_t offset=$offset;")[attr]
            body += T("\n  $type* data = ($type*)(((const char*)this)+offset);")(type=_typename(attr.type))
            body += T("\n  return make_ndarray(data, $shape);")(shape=shape)
            return body

    def _bodyAnyArrray(self, attr):
        """Makes method body for methods returning ndarray"""

        shape = ', '.join([str(s or 0) for s in attr.shape.dims])
        if attr.isfixed():

            return T("return $name$dimexpr;")(name=attr.name, dimexpr=_dimexpr(attr.shape.dims))

        elif attr.type.variable:
            
            # _sizeof may need config
            sizeofCfg = ''
            if str(attr.type.size).find('{xtc-config}') >= 0: 
                sizeofCfg = '{xtc-config}'
                
            typename = _typename(attr.type)
            body = T("const char* memptr = ((const char*)this)+$offset;")[attr]
            body += "\n  for (uint32_t i=0; i != i0; ++ i) {"
            body += T("\n    memptr += ((const $typename*)memptr)->_sizeof($sizeofCfg);")(locals())
            body += "\n  }"
            body += T("\n  return *(const $typename*)(memptr);")(locals())
            return body

        else:
            
            idxexpr = ExprVal('i0', self._type)
            for i in range(1,len(attr.shape.dims)):
                idxexpr = idxexpr*attr.shape.dims[i] + ExprVal('i%d'%i, self._type)
                
            # _sizeof may need config
            sizeofCfg = ''
            if str(attr.type.size).find('{xtc-config}') >= 0: 
                sizeofCfg = '{xtc-config}'

            typename = _typename(attr.type)
            body = T("ptrdiff_t offset=$offset;")[attr]
            body += T("\n  const $typename* memptr = (const $typename*)(((const char*)this)+offset);")(locals())
            body += T("\n  size_t memsize = memptr->_sizeof($sizeofCfg);")(locals())
            body += T("\n  return *(const $typename*)((const char*)memptr + ($idxexpr)*memsize);")(locals())
            return body


    def _genMethodExpr(self, methname, rettype, expr, args=[], inline=False, static=False, doc=None):
        """ Generate method, both declaration and definition, given the expression that it returns"""

        body = expr
        if body and rettype != 'void': body = T("return $expr;")(locals())
        self._genMethodBody(methname, rettype, body, args=args, inline=inline, static=static, doc=doc)
        
    def _genMethodBody(self, methname, rettype, body, args=[], inline=False, static=False, doc=None):
        """ Generate method, both declaration and definition, given the body of the method"""
        
        # make argument list
        argsspec = ', '.join([_argdecl(*arg) for arg in args])

        if self._pywrapper:
            policy = ""
            args = ', '.join([_argdecl2(*arg) for arg in args])
            index = rettype.find("ndarray<")
            if index == 0:
                ctype_ndim = rettype[8:]
                index = ctype_ndim.rfind(">")
                if index != -1:
                    ctype_ndim = ctype_ndim[:index]
                index = ctype_ndim.find(", ")
                ctype = ctype_ndim[:index]
                ndim = int(ctype_ndim[index + 2:])
                if ndim == 1 or "::" in ctype:
                    if ndim > 1:
                        print "WARNING: cannot generate ndarray<%s, %d>, so generating one-dimensional std::vector<%s> instead" % (ctype, ndim, ctype)
                    print >>self._inc, T("  std::vector<$ctype> $methname($argsspec) const { VEC_CONVERT(o->$methname($args), $ctype); }")(locals())
                else:
                    print >>self._inc, T("  PyObject* $methname($argsspec) const { ND_CONVERT(o->$methname($args), $ctype, $ndim); }")(locals())
            elif "&" in rettype and "::" in rettype:
                type = rettype.replace("&", "").replace("const ", "")
                index = type.find("::")
                if index != -1:
                    type = type[2+index:] # remove "Namespace::"
                wrappertype = type + "_Wrapper"
                print >>self._inc, T("  const $wrappertype $methname($argsspec) const { return $wrappertype(($type*) &o->$methname($args)); }")(locals())
                policy = ", policy"
            else:
                print >>self._inc, T("  $rettype $methname($argsspec) const { return o->$methname($args); }")(locals())

            print >>self._cpp, T("    .def(\"$methname\", &n::$methname$policy)\\")(methname=methname, classname=self._type.name, policy=policy)
            return

        if static:
            static = "static "
            const = ""
        else:
            static = ""
            const = "const"
        

        if doc: print >>self._inc, T('  /** $doc */')(locals())

        if self._abs and not static:
            
            # abstract method declaration, body is not needed
            print >>self._inc, T("  virtual $rettype $methname($argsspec) const = 0;")(locals())

        elif not body:

            # declaration only, implementation provided somewhere else
            print >>self._inc, T("  $static$rettype $methname($argsspec) $const;")(locals())

        elif inline:
            
            # inline method
            print >>self._inc, T("  $static$rettype $methname($argsspec) $const { $body }")(locals())
        
        else:
            
            # out-of-line method
            classname = self._type.name
            print >>self._inc, T("  $static$rettype $methname($argsspec) $const;")(locals())
            print >>self._cpp, T("$rettype\n$classname::$methname($argsspec) $const {\n  $body\n}")(locals())



    def _genCtor(self, ctor):

        # find attribute for a given name
        def name2attr(name):
            
            if not name: return None
            
            # try argument name
            attr = self._type.localName(name)
            if isinstance(attr, Attribute): return attr
            
            # look for bitfield names also
            for attr in self._type.attributes():
                for bf in attr.bitfields:
                    if bf.name == name: return bf
                    
            raise ValueError('No attrubute or bitfield with name %s defined in type %s' % (name, self._type.name))
            
        args = ctor.args
        if not args :
            
            if 'auto' in ctor.tags:
                # make one argument per type attribute
                for attr in self._type.attributes():
                    if attr.bitfields:
                        for bf in attr.bitfields:
                            if bf.accessor:
                                name = "arg_bf_"+bf.name
                                type = bf.type
                                dest = bf
                                args.append((name, type, dest))
                    else:
                        name = "arg_"+attr.name
                        type = attr.type
                        dest = attr
                        args.append((name, type, dest))
        
        else:
            
            # convert destination names to attribute objects
            args = [(name, type, name2attr(dest)) for name, type, dest in args]

        # map attributes to arguments
        attr2arg = {}
        for name, type, dest in args:
            attr2arg[dest] = name

        # argument list for declaration
        arglist = []
        for argname, argtype, attr in args:
            if not argtype: argtype = attr.type
            tname = _typename(argtype)
            if isinstance(attr,Attribute) and attr.shape:
                tname = "const "+tname+'*'
            elif not attr.type.basic : 
                tname = "const "+tname+'&'
            arglist.append(tname+' '+argname)
        arglist = ", ".join(arglist)

        # initialization list
        initlist = []
        for attr in self._type.attributes():
            arg = attr2arg.get(attr,"")
            if attr.shape:
                init = ''
            elif arg :
                init = arg
            elif attr.bitfields:
                # there may be arguments initializing individual bitfields
                bfinit = []
                for bf in attr.bitfields:
                    bfarg = attr2arg.get(bf)
                    if bfarg: bfinit.append(bf.assignExpr(bfarg))
                init = '|'.join(bfinit)
            elif attr.name in ctor.attr_init:
                init = ctor.attr_init[attr.name]
            else:
                init = ""
            if init: initlist.append(T("$attr($init)")(attr=attr.name, init=init))

        # do we need generate definition too?
        if 'c++-definition' in ctor.tags:
            genDef = True
        elif 'no-c++-definition' in ctor.tags:
            genDef = False
        else:
            # generate definition only if all destinations are known
            genDef = None not in [dest for name, type, dest in args]

        if not genDef:
            
            # simply a declaration
            print >>self._inc, T("  $name($args);")(name=self._type.name, args=arglist)

        elif 'inline' in ctor.tags:
            
            # inline the definition
            print >>self._inc, T("  $name($args)")(name=self._type.name, args=arglist)
            if initlist: print >>self._inc, "    :", ', '.join(initlist)
            print >>self._inc, "  {"
            for attr in self._type.attributes():
                arg = attr2arg.get(attr,"")
                if attr.shape and arg:
                    size = attr.shape.size()
                    first = '[0]' * (len(attr.shape.dims)-1)
                    print >>self._inc, T("    std::copy($arg, $arg+($size), $attr$first);")(locals(), attr=attr.name)
            print >>self._inc, "  }"

        else:
            
            # out-line the definition
            print >>self._inc, T("  $name($args);")(name=self._type.name, args=arglist)

            print >>self._cpp, T("$name::$name($args)")(name=self._type.name, args=arglist)
            if initlist: print >>self._cpp, "    :", ', '.join(initlist)
            print >>self._cpp, "{"
            for attr in self._type.attributes():
                arg = attr2arg.get(attr,"")
                if attr.shape and arg:
                    size = attr.shape.size()
                    first = '[0]' * (len(attr.shape.dims)-1)
                    print >>self._inc, T("  std::copy($arg, $arg+($size), $attr$first);")(locals(), attr=attr.name)
            print >>self._cpp, "}"


    def _genAttrShapeDecl(self, attr):

        if not attr.shape_method: return 
        if not attr.accessor: return
        
        doc = "Method which returns the shape (dimensions) of the data returned by %s() method." % \
                attr.accessor.name
        
        # value-type arrays return ndarrays which do not need shape method
        if attr.type.value_type and attr.type.name != 'char': return

        shape = [str(s or -1) for s in attr.shape.dims]

        body = "std::vector<int> shape;" 
        body += T("\n  shape.reserve($size);")(size=len(shape))
        for s in shape:
            body += T("\n  shape.push_back($dim);")(dim=s)
        body += "\n  return shape;"

        # guess if we need to pass cfg object to method
        cfgNeeded = body.find('{xtc-config}') >= 0
        body = _interpolate(body, self._type)

        configs = [None]
        if cfgNeeded and not self._abs: configs = attr.parent.xtcConfig
        for cfg in configs:

            cargs = []
            if cfg: cargs = [('cfg', cfg)]

            self._genMethodBody(attr.shape_method, "std::vector<int>", body, cargs, inline=False, doc=doc)



#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )