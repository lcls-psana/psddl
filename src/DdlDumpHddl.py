#--------------------------------------------------------------------------
# File and Version Information:
#  $Id$
#
# Description:
#  Module DdlDumpHddl...
#
#------------------------------------------------------------------------

"""psddlc backend which dumps model in human-ddl format.

This software was developed for the LCLS project.  If you use all or 
part of it, please give an appropriate acknowledgment.

@version $Id$

@author Andy Salnikov
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

#---------------------------------
#  Imports of base class module --
#---------------------------------


#-----------------------------
# Imports for other modules --
#-----------------------------
from psddl.Package import Package
from psddl.Type import Type
from psddl.Template import Template as T

#----------------------------------
# Local non-exported definitions --
#----------------------------------
def _fmttags(tags):
    if tags: return '\n  '.join(['[[{0}]]'.format(tag) for tag in tags])
    return ''

def _fmttags1(tags):
    if tags: return '[[{0}]]'.format(', '.join(tags))
    return ''

def _dims(dims):
    return "[{0}]".format(', '.join([str('*' if d is None else d) for d in dims]))

def _codesubs(expr):
    expr = expr.replace('{xtc-config}', '@config')
    expr = expr.replace('{type}.', '@class.')
    expr = expr.replace('{self}.', "@self.")
    return expr


#------------------------
# Exported definitions --
#------------------------

#---------------------
#  Class definition --
#---------------------
class DdlDumpHddl ( object ) :

    @staticmethod
    def backendOptions():
        """ Returns the list of options supported by this backend, returned value is 
        either None or a list of triplets (name, type, description)"""
        return None

    #----------------
    #  Constructor --
    #----------------
    def __init__ ( self, backend_options, log ) :
        '''Constructor
        
           @param backend_options  dictionary of options passed to backend
           @param log              message logger instance
        '''
        self.outname = backend_options['global:source']

        self._log = log


    #-------------------
    #  Public methods --
    #-------------------

    def parseTree ( self, model ) :
        
        # open output files
        self.out = file(self.outname, 'w')

        # headers for other included packages
        for use in model.use:
            headers = use['cpp_headers']
            if not headers:
                print >>self.out, 'use "{0}";'.format(use['file'])
            else:
                names = ', '.join(['"{0}"'.format(header) for header in headers])
                names = _fmttags(['headers({0})'.format(names)])
                print >>self.out, 'use "{0}" {1};'.format(use['file'], names)

        # loop over packages in the model
        for pkg in model.packages() :
            if not pkg.included :
                self._log.debug("parseTree: package=%s", repr(pkg))
                self._genPackage(pkg)

        # close all files
        self.out.close()


    def _genPackage(self, pkg):


        tags = []
        if pkg.external: tags.append('external')
        if 'c++-name' in pkg.tags: tags.append('cpp_name("{0}")'.format(pkg.tags['c++-name']))
        tags = _fmttags(tags)

        # open package
        print >>self.out, T("package $name $tags {")(name=pkg.name, tags=tags)

        # constants
        for const in pkg.constants():
            if not const.included:
                self._genConst(const)

        # regular enums
        for enum in pkg.enums() :
            if not enum.included :
                self._genEnum(enum)

        # loop over packages and types
        for ns in pkg.namespaces() :
            
            if isinstance(ns, Package) :
                
                self._genPackage(ns)
            
            elif isinstance(ns, Type) :
    
                self._genType(type = ns)

        # close package
        print >>self.out, T("} //- package $name")[pkg]

    def _genConst(self, const):
        
        if const.comment:
            print >>self.out, T("  /* $comment */\n  const int $name = $value;")[const]
        else:
            print >>self.out, T("  const int $name = $value;")[const]


    def _genEnum(self, enum):

        if not enum.name: return

        base = enum.base.name
        if enum.comment:
            print >>self.out, T("  /* $comment */\n  enum $name ($base) {")(name=enum.name, base=base, comment=enum.comment)
        else:
            print >>self.out, T("  enum $name ($base) {")(name=enum.name, base=base)
        
        for const in enum.constants() :
            val = ""
            if const.value is not None : val = " = " + const.value
            doc = ""
            if const.comment: doc = T(' /* $comment */')[const]
            print >>self.out, T("    $name$value,$doc")(name=const.name, value=val, doc=doc)
        print >>self.out, "  }"

    def _genType(self, type):

        self._log.debug("_genType: type=%s", repr(type))

        # skip included types
        if type.included : return

        print >>self.out, T("\n\n//------------------ $name ------------------")[type]

        tags = []
        if type.type_id: tags.append('type_id({0}, {1})'.format(type.type_id, type.version))
        if type.external: tags.append('external')
        if type.value_type: tags.append('value_type')
        if 'config-type' in type.tags: tags.append('config_type')
        if 'c++-name' in type.tags: tags.append('cpp_name("{0}")'.format(pkg.tags['c++-name']))
        if 'no-sizeof' in type.tags: tags.append('no_sizeof')
        if type.pack: tags.append('pack({0})'.format(type.pack))
        if type.xtcConfig:
            types = ', '.join([T("$name")[cfg] for cfg in type.xtcConfig])
            tags.append('xtc_config({0})'.format(types))
        
        tags = _fmttags(tags)

        base = ""
        if type.base : base = T("($name)")[type.base]

        # start class decl
        if type.comment: print >>self.out, T("/* $comment */")[type]
        print >>self.out, T("class $name$base")(name=type.name, base=base)
        if tags: print >>self.out, "  " + tags
        print >>self.out, "{"

        # constants
        for const in type.constants():
            self._genConst(const)
        if type.constants(): print >>self.out

        # regular enums
        for enum in type.enums() :
            self._genEnum(enum)
        if type.enums(): print >>self.out

        # constructors
        for ctor in type.ctors:
            self._genCtor(ctor)
        if type.ctors: print >>self.out

        # attributes
        for attrib in type.attributes():
            self._genAttrib(attrib)
        
        # methods
        for meth in type.methods():
            self._genMethod(meth)
        

        print >>self.out, "}"


    def _genAttrib(self, attr):

        # use full name if not in a global namespace and not in type's namespace (or in type itself)
        if attr.type.parent.name and not (attr.type.parent is attr.parent.parent or attr.type.parent is attr.parent):
            typename = attr.type.fullName()
        else:
            typename = attr.type.name
            
        comment = T("\t/* $comment */")[attr] if attr.comment else ''
        method = T(" -> $name")[attr.accessor] if attr.accessor else ''
        
        tags = []
        if attr.shape_method: tags.append('shape_method("{0}")'.format(attr.shape_method))
        tags = _fmttags(tags)
        if tags: tags = '  '+tags
        
        name = attr.name
        
        if not attr.bitfields:
            shape = ''
            if attr.shape:
                shape = _codesubs(_dims(attr.shape.dims))
            
            print >>self.out, T("  $typename $name$shape$method$tags;$comment")(locals())
        else:
            print >>self.out, T("  $typename $name$method$tags {$comment")(locals())
            
            for bf in attr.bitfields:
                
                typename = bf.type.name
                name = bf.name
                method = T(" -> $name")[bf.accessor] if bf.accessor else ''
                comment = T("\t/* $comment */")[bf] if bf.comment else ''
                size = bf.size

                print >>self.out, T("    $typename $name:$size$method;$comment")(locals())
            
            print >>self.out, "  }"


    def _genMethod(self, meth):
        
        # accessor methods are defined by attributes
        if meth.attribute or meth.bitfield: return

        # sizeof is not declared
        if meth.name == "_sizeof": return

        # use full name if not in a global namespace and not in type's namespace (or in type itself)
        if meth.type is None:
            typename = 'void'
        elif meth.type.parent.name and not (meth.type.parent is meth.parent.parent or meth.type.parent is meth.parent):
            typename = meth.type.fullName()
        else:
            typename = meth.type.name
        if meth.rank: typename = typename + '[]'*meth.rank

        tags = []
        if 'inline' in meth.tags: tags.append('inline')
        tags = _fmttags1(tags)
        if tags: tags = '  '+tags

        args = []
        for arg in meth.args:
            args.append('{0} {1}'.format(arg[1].name, arg[0]))
        args = ', '.join(args)
        
        print >>self.out, ""
        if meth.comment: print >>self.out, T("  /* $comment */")[meth]
        name = meth.name

        if meth.code:
            print >>self.out, T("  $typename $name($args)$tags")(locals())
            for lang, code in meth.code.items():
                tags = _fmttags(['language("{0}")'.format(lang)])
                print >>self.out, T("  %{ $tags")(locals())
                print >>self.out, _codesubs(code)
                print >>self.out, "  %}"
        elif meth.expr:
            print >>self.out, T("  $typename $name($args)$tags")(locals())
            for lang, code in meth.expr.items():
                tags = _fmttags(['language("{0}")'.format(lang)])
                print >>self.out, T("  %{ $tags")(locals())
                print >>self.out, "    return " + _codesubs(code) + ';'
                print >>self.out, "  %}"
        else:
            print >>self.out, T("  $typename $name($args) [[external]]$tags;")(locals())



    def _genCtor(self, ctor):

        tags = []
        if 'auto' in ctor.tags: tags.append('auto')
        if 'inline' in ctor.tags: tags.append('inline')
        if 'force_definition' in ctor.tags: tags.append('force_definition')
        if 'external' in ctor.tags or \
            ('force_definition' not in ctor.tags and None in [arg.dest for arg in ctor.args]):
            tags.append('external')
        tags = _fmttags1(tags)
        if tags: tags = '  '+tags

        args = []
        arginits = []
        for arg in ctor.args:
            adecl = None
            ainit = None
            if arg.dest and arg.expr == arg.name:
                # argument itself is used to initialize destination
                if arg.type is arg.dest.type:
                    adecl = '{0} -> {1}'.format(arg.name, arg.dest.name)
                else:
                    adecl = '{0} {1} -> {2}'.format(arg.type.name, arg.name, arg.dest.name)
            elif arg.dest:
                # Expression is used to initialize destination, declare argument with a type and
                # define initialization expression
                adecl = '{0} {1}'.format(arg.type.name, arg.name)
                ainit = '{0}({1})'.format(arg.dest.name, arg.expr)
            else:
                # just declare argument
                adecl = '{0} {1}'.format(arg.type.name, arg.name)
                
            if arg.method and (not arg.dest or arg.dest.accessor is not arg.method):
                # add special method for this argument
                adecl = adecl + ' ' + _fmttags1(['method({0})'.format(arg.method.name)])

            args.append(adecl)
            if ainit: arginits.append(ainit)
            
        for arginit in ctor.attr_init:
            ainit = '{0}({1})'.format(arginit.dest.name, arginit.expr)
                
        args = ', '.join(args)
        arginits = ', '.join(arginits)
        
        print >>self.out, ""
        if ctor.comment: print >>self.out, T("  /* $comment */")[ctor]

        if 'auto' in ctor.tags:
            print >>self.out, T("  init()$tags;")(locals())
        elif arginits:
            print >>self.out, T("  init($args)$tags\n    $arginits;")(locals())
        else:
            print >>self.out, T("  init($args)$tags;")(locals())


#
#  In case someone decides to run this module
#
if __name__ == "__main__" :

    # In principle we can try to run test suite for this module,
    # have to think about it later. Right now just abort.
    sys.exit ( "Module is not supposed to be run as main module" )
