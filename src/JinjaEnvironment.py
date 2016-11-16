import jinja2 as ji

from psddl.TemplateLoader import TemplateLoader

def getJinjaEnvironment(package=None, templateSubDir=None):
    if package is None and templateSubDir is None:
        loader = TemplateLoader()
    else:
        assert package and templateSubDir, "if setting one of package/templateSubDir, must set the other"
        loader = TemplateLoader(package=package, templateSubDir=templateSubDir)
    jiEnv = ji.Environment(loader=loader,
                           cache_size=0,
                           trim_blocks=True,
                           line_statement_prefix='$',
                           line_comment_prefix='$$')
    return jiEnv
