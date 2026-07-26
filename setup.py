from setuptools import setup, Extension
from setuptools.command.build_ext import build_ext
import os
import sys
import sysconfig
import glob

try:
    from numpy.distutils.ccompiler import CCompiler_compile
    import distutils.ccompiler
    distutils.ccompiler.CCompiler.compile = CCompiler_compile
except ImportError:
    pass

NAME = 'skia-python'
__version__ = '144.0.post2'

SKIA_PATH = os.getenv('SKIA_PATH', 'skia')
SKIA_OUT_PATH = os.getenv(
    'SKIA_OUT_PATH', os.path.join(SKIA_PATH, 'out', 'Release')
)

# --- Sulphur fork: link against the project's prebuilt Skia.xcframework ---
# On macOS we do NOT build our own Skia copy. We consume the exact same
# universal, Vulkan-only libskia.a (m144, built by skia-build/) that the
# Swift app statically links — the only way the SkSurface* handed over the
# PyCapsule stays ABI-compatible across the boundary. The xcframework's
# Headers/ tree (include/ + modules/) is the sole include root; the module
# archives (svg/skparagraph/skshaper/skunicode) sit alongside libskia.a in
# the slice dir and are linked together. Override the location with
# SKIA_XCFRAMEWORK when building out-of-tree.
_HERE = os.path.dirname(os.path.abspath(__file__))
SKIA_XCFRAMEWORK = os.getenv(
    'SKIA_XCFRAMEWORK',
    os.path.join(
        _HERE, os.pardir, 'SulphurXcodeDemo', 'packages', 'PyNucleantUI',
        'Dependencies', 'Skia.xcframework',
    ),
)


def _skia_macos_slice():
    """Path to the macOS (universal) slice dir inside the xcframework."""
    slices = sorted(glob.glob(os.path.join(SKIA_XCFRAMEWORK, 'macos-*')))
    if not slices:
        raise SystemExit(
            f"no macos-* slice under {SKIA_XCFRAMEWORK} — build/install "
            f"Skia.xcframework first (skia-build/build_skia_macos.py) or set "
            f"SKIA_XCFRAMEWORK."
        )
    return slices[0]


def _ios_platform_tag():
    """The current build's platform tag, e.g. 'ios-13.0-x86_64-iphonesimulator'.
    cibuildwheel's cross venv doesn't set _PYTHON_HOST_PLATFORM/PLATFORM_NAME (those
    are Xcode/CPython-cross-build conventions, not ones cibuildwheel populates), but
    sysconfig.get_platform() still resolves it correctly off the target interpreter
    itself — it's what distutils uses internally to name the build/temp dirs."""
    return (
        os.environ.get('_PYTHON_HOST_PLATFORM')
        or os.environ.get('PLATFORM_NAME')
        or sysconfig.get_platform()
    ).lower()


def _is_ios_build():
    """iOS wheels build under a macOS host Python (sys.platform=='darwin'), so
    detect the iOS target from the platform tag instead."""
    if sys.platform == 'ios':
        return True
    tag = _ios_platform_tag()
    return 'ios' in tag or 'iphone' in tag


def _skia_ios_slice():
    """The iOS device or simulator slice dir inside the xcframework, chosen from
    the current build's platform tag."""
    tag = _ios_platform_tag()
    is_sim = 'simulator' in tag or 'iphonesimulator' in tag
    slices = sorted(glob.glob(os.path.join(SKIA_XCFRAMEWORK, 'ios-*')))
    cands = [s for s in slices
             if ('simulator' in os.path.basename(s)) == is_sim]
    if not cands:
        raise SystemExit(
            f"no {'simulator' if is_sim else 'device'} ios-* slice under "
            f"{SKIA_XCFRAMEWORK} — build Skia.xcframework's iOS slices "
            f"(skia-build/build_skia_ios.py) or set SKIA_XCFRAMEWORK."
        )
    return cands[0]

data_files = []
if sys.platform == 'win32':
    DEFINE_MACROS = []  # doesn't work for cl.exe
    LIBRARIES = [
        'FontSub',
        'Ole32',
        'OleAut32',
        'User32',
        'Usp10',
        'OpenGL32',
        'Gdi32',
        'Advapi32',
    ]
    EXTRA_OBJECTS = list(
    ) + [os.path.join(SKIA_OUT_PATH, 'svg.lib'), os.path.join(SKIA_OUT_PATH, 'skresources.lib'), os.path.join(SKIA_OUT_PATH, 'skia.lib'),
         os.path.join(SKIA_OUT_PATH, 'skparagraph.lib'), os.path.join(SKIA_OUT_PATH, 'skshaper.lib'),
         os.path.join(SKIA_OUT_PATH, 'skunicode_icu.lib'), os.path.join(SKIA_OUT_PATH, 'skunicode_core.lib')]
    EXTRA_COMPILE_ARGS = [
        '/std:c++17',  # c++20 fails.
        '/DVERSION_INFO=%s' % __version__,
        '/DSK_GL',
        '/DSK_VULKAN',
        '/DSK_GANESH=1',
        '/Zc:inline',
        # Disable a bunch of warnings.
        '/wd5030',  # Warnings about unknown attributes.
        '/wd4244',  # Conversion from 'float' to 'int', possible loss of data.
        '/wd4267',  # Conversion from 'size_t' to 'int', possible loss of data.
        '/wd4800',  # Forcing value to bool 'true' or 'false'.
        '/wd4180',  # Qualifier applied to function type has no meaning.
        '/MD',  # Bugfix: https://bugs.python.org/issue38597
    ]
    EXTRA_LINK_ARGS = [
        '/OPT:ICF',
        '/OPT:REF',
    ]
    data_files = [('Lib/site-packages', [os.path.join(SKIA_OUT_PATH, 'icudtl.dat')])]
elif _is_ios_build():
    # iOS: link the exact static libskia.a (+ module archives) from the
    # xcframework's iOS slice — same ABI as the Swift app's Skia, so the
    # SkSurface* handed over the PyCapsule stays compatible. Vulkan-only Ganesh
    # (MoltenVK at runtime), same as macOS.
    SKIA_SLICE = _skia_ios_slice()
    SKIA_HEADERS = os.path.join(SKIA_SLICE, 'Headers')
    SKIA_SOURCE = os.getenv(
        'SKIA_SOURCE', os.path.join(_HERE, os.pardir, 'skia-build', 'skia'),
    )
    _skia_gen = sorted(glob.glob(os.path.join(SKIA_SOURCE, 'out', '*', 'gen')))
    SKIA_GEN = _skia_gen[-1] if _skia_gen else None
    DEFINE_MACROS = [
        ('VERSION_INFO', __version__),
        ('SK_GANESH', '1'),
        ('SK_VULKAN', ''),
    ]
    LIBRARIES = ['dl']
    EXTRA_OBJECTS = [
        os.path.join(SKIA_SLICE, name)
        for name in (
            'libsvg.a', 'libskia.a', 'libskparagraph.a', 'libskshaper.a',
            'libskunicode_icu.a', 'libskunicode_core.a',
        )
        if os.path.isfile(os.path.join(SKIA_SLICE, name))
    ]
    if not any(o.endswith('libskia.a') for o in EXTRA_OBJECTS):
        raise SystemExit(
            f"libskia.a not found in {SKIA_SLICE} — rebuild the Skia.xcframework "
            f"iOS slices (skia-build/build_skia_ios.py)."
        )
    EXTRA_COMPILE_ARGS = [
        '-std=c++17',
        '-stdlib=libc++',
        '-fvisibility=hidden',
    ]
    # Apple frameworks Skia's iOS CoreText fontmgr / codecs need. NOT AppKit /
    # ApplicationServices (macOS-only). cibuildwheel's clang sets the iOS
    # target/sysroot + min-version; Vulkan resolves via the app's MoltenVK.
    EXTRA_LINK_ARGS = [
        '-stdlib=libc++',
        '-dead_strip',
        '-framework', 'CoreFoundation',
        '-framework', 'CoreGraphics',
        '-framework', 'CoreText',
        '-framework', 'ImageIO',
        '-framework', 'UIKit',
    ]
elif sys.platform == 'darwin':
    SKIA_SLICE = _skia_macos_slice()
    SKIA_HEADERS = os.path.join(SKIA_SLICE, 'Headers')
    # The xcframework's public headers are not enough to *compile* against:
    # several module public headers (e.g. SkResources.h, pulled in by
    # SkSVGDOM.h) include Skia's internal "src/..." headers, which are not
    # part of any public/shippable API. skia-python's own build resolves
    # those against the full Skia source tree, so we do the same — this only
    # affects compile-time includes; the actual binary still comes from the
    # xcframework archives. Points at the co-located m144 checkout that
    # produced this very xcframework (override with SKIA_SOURCE).
    SKIA_SOURCE = os.getenv(
        'SKIA_SOURCE', os.path.join(_HERE, os.pardir, 'skia-build', 'skia'),
    )
    # Generated headers (e.g. GrDriverBugWorkaroundsAutogen.h) live under the
    # ninja out dir's gen/. The autogen one is also baked into SKIA_HEADERS,
    # but include the gen dir too for any others.
    _skia_gen = sorted(glob.glob(os.path.join(SKIA_SOURCE, 'out', '*', 'gen')))
    SKIA_GEN = _skia_gen[-1] if _skia_gen else None
    # Vulkan-only Ganesh: no GL, no Metal. The Vulkan backend links no
    # Vulkan library — Skia resolves every entry point through the
    # vkGetInstanceProcAddr the host app (MoltenVK, via CVulkan) hands its
    # GrDirectContext, so there is nothing to link here.
    DEFINE_MACROS = [
        ('VERSION_INFO', __version__),
        ('SK_GANESH', '1'),
        ('SK_VULKAN', ''),
    ]
    LIBRARIES = [
        'dl',
    ]
    # libskia.a is complete_static_lib (core + folded third_party: freetype,
    # expat, png/jpeg/webp, zlib, icu data). The module archives carry only
    # their own objects + exclusive deps (harfbuzz/icu into skunicode/
    # skshaper/skparagraph). Link only the ones the build actually produced.
    EXTRA_OBJECTS = [
        os.path.join(SKIA_SLICE, name)
        for name in (
            'libsvg.a', 'libskia.a', 'libskparagraph.a', 'libskshaper.a',
            'libskunicode_icu.a', 'libskunicode_core.a',
        )
        if os.path.isfile(os.path.join(SKIA_SLICE, name))
    ]
    if not any(o.endswith('libskia.a') for o in EXTRA_OBJECTS):
        raise SystemExit(
            f"libskia.a not found in {SKIA_SLICE} — rebuild Skia.xcframework."
        )
    EXTRA_COMPILE_ARGS = [
        '-std=c++17',
        '-stdlib=libc++',
        '-mmacosx-version-min=11.0',
        '-fvisibility=hidden',
    ]
    EXTRA_LINK_ARGS = [
        '-stdlib=libc++',
        '-mmacosx-version-min=11.0',
        '-dead_strip',
        '-framework',
        'AppKit',
        '-framework',
        'ApplicationServices',
    ]
else:
    DEFINE_MACROS = [
        ('VERSION_INFO', __version__),
        ('SK_GL', ''),
        ('SK_VULKAN', ''),
        ('SK_GANESH', '1'),
    ]
    LIBRARIES = [
        'dl',
        'fontconfig',
        'EGL',
        'GL',
        'expat',
    ]
    EXTRA_OBJECTS = list(
    ) + [os.path.join(SKIA_OUT_PATH, 'libsvg.a'), os.path.join(SKIA_OUT_PATH, 'libskresources.a'), os.path.join(SKIA_OUT_PATH, 'libskia.a'),
         os.path.join(SKIA_OUT_PATH, 'libskparagraph.a'), os.path.join(SKIA_OUT_PATH, 'libskshaper.a'),
         os.path.join(SKIA_OUT_PATH, 'libskunicode_icu.a'), os.path.join(SKIA_OUT_PATH, 'libskunicode_core.a')]
    EXTRA_COMPILE_ARGS = [
        '-std=c++17',
        '-fvisibility=hidden',
        '-Wno-attributes',
        '-fdata-sections',
        '-ffunction-sections',
    ]
    EXTRA_LINK_ARGS = [
        '-Wl,--gc-sections',
        '-s',
        '-O3',
    ]


class get_pybind_include(object):
    """Helper class to determine the pybind11 include path

    The purpose of this class is to postpone importing pybind11
    until it is actually installed, so that the ``get_include()``
    method can be invoked. """
    def __init__(self, user=False):
        self.user = user

    def __str__(self):
        import pybind11
        return pybind11.get_include(self.user)


class BuildExt(build_ext):
    """A custom build extension for adding compiler-specific options."""
    def build_extensions(self):
        if sys.platform == 'linux':
            try:
                self.compiler.compiler_so.remove('-Wstrict-prototypes')
            except (AttributeError, ValueError):
                pass
        build_ext.build_extensions(self)


if _is_ios_build() or sys.platform == 'darwin':
    # Include order: the xcframework's public + module headers first (Skia's
    # own layout — include/... and modules/.../include — plus the baked
    # GrDriverBugWorkaroundsAutogen.h), then the Skia source checkout for the
    # internal "src/..." headers that some module public headers leak, then
    # the gen/ dir for any other generated headers. Vulkan backend headers
    # come from include/third_party/vulkan.
    INCLUDE_DIRS = [
        get_pybind_include(),
        get_pybind_include(user=True),
        SKIA_HEADERS,
        os.path.join(SKIA_HEADERS, "include/third_party/vulkan"),
        SKIA_SOURCE,
        os.path.join(SKIA_SOURCE, "include/third_party/vulkan"),
    ]
    if SKIA_GEN:
        INCLUDE_DIRS.append(SKIA_GEN)
else:
    INCLUDE_DIRS = [
        get_pybind_include(),
        get_pybind_include(user=True),
        SKIA_PATH,
        os.path.join(SKIA_PATH, "third_party/externals/freetype/include"),
        os.path.join(SKIA_PATH, "third_party/externals/vulkan-headers/include"),
        os.path.join(SKIA_PATH, "include/third_party/vulkan"),
        os.path.join(SKIA_OUT_PATH, 'gen'),
    ]

extension = Extension(
    'skia',
    sources=list(glob.glob(os.path.join('src', 'skia', '*.cpp'))),
    include_dirs=INCLUDE_DIRS,
    define_macros=DEFINE_MACROS,
    libraries=LIBRARIES,
    extra_objects=EXTRA_OBJECTS,
    extra_compile_args=EXTRA_COMPILE_ARGS,
    extra_link_args=EXTRA_LINK_ARGS,
    depends=[os.path.join('src', 'skia', 'common.h')],
    language='c++',
)

setup(
    name=NAME,
    version=__version__,
    author='Kota Yamaguchi',
    author_email='KotaYamaguchi1984@gmail.com',
    url='https://github.com/kyamagu/skia-python',
    description='Skia python binding',
    long_description=open('README.md', 'r').read(),
    long_description_content_type='text/markdown',
    ext_modules=[extension],
    data_files=data_files,
    install_requires=[
        'numpy',
        'pybind11>=2.6'
    ],
    setup_requires=['pybind11>=2.6'],
    cmdclass={'build_ext': BuildExt},
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: End Users/Desktop',
        'License :: OSI Approved :: BSD License',
        'Operating System :: MacOS :: MacOS X',
        'Operating System :: Microsoft :: Windows',
        'Operating System :: POSIX',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
        'Programming Language :: Python :: 3.12',
        'Programming Language :: Python :: 3.13',
        'Topic :: Multimedia :: Graphics',
        'Topic :: Scientific/Engineering :: Visualization',
    ],
    zip_safe=False,
)
