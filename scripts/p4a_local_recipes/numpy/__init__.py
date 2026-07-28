from pythonforandroid.recipe import MesonRecipe, Recipe
from os.path import join
import shutil

NUMPY_NDK_MESSAGE = (
    "In order to build numpy, you must set minimum ndk api (minapi) to `24`.\n"
)


class NumpyRecipe(MesonRecipe):
    version = "v2.3.0"
    url = "git+https://github.com/numpy/numpy"
    extra_build_args = ["-Csetup-args=-Dblas=none", "-Csetup-args=-Dlapack=none"]
    opt_depends = ["libopenblas"]
    need_stl_shared = True
    min_ndk_api_support = 24

    # Local override: upstream numpy 2.3.0 unique.cpp includes <unordered_set>
    # but uses std::unordered_map. Android NDK r25b clang-14 + libc++ has no
    # transitive include, so the file fails to compile. This patch adds the
    # missing include. Remove once numpy upstream or p4a ships a fix.
    patches = ["patches/numpy_unordered_map_include.patch"]

    def get_include(self, arch):
        return join(
            self.ctx.get_python_install_dir(arch.arch), "numpy/_core/include",
        )

    def get_recipe_meson_options(self, arch):
        options = super().get_recipe_meson_options(arch)
        options["properties"]["longdouble_format"] = (
            "IEEE_DOUBLE_LE" if arch.arch in ["armeabi-v7a", "x86"] else "IEEE_QUAD_LE"
        )
        return options

    def get_recipe_env(self, arch, **kwargs):
        env = super().get_recipe_env(arch, **kwargs)
        env["_PYTHON_HOST_PLATFORM"] = arch.command_prefix
        env["NPY_DISABLE_SVML"] = "1"
        env["TARGET_PYTHON_EXE"] = join(
            Recipe.get_recipe("python3", self.ctx).get_build_dir(arch.arch),
            "android-build",
            "python",
        )
        blas_dir = join(
            Recipe.get_recipe("libopenblas", self.ctx).get_build_dir(arch.arch),
            "build",
        )
        blas_incdir = blas_dir
        blas_libdir = join(blas_dir, "lib")
        env["CXXFLAGS"] += f" -I{blas_incdir} -L{blas_libdir}"

        if "libopenblas" in self.ctx.recipe_build_order:
            self.extra_build_args = [
                "-Csetup-args=-Dblas=auto",
                "-Csetup-args=-Dlapack=auto",
                "-Csetup-args=-Dallow-noblas=False",
            ]

        return env

    def get_hostrecipe_env(self, arch=None):
        env = super().get_hostrecipe_env(arch=arch)
        env["RANLIB"] = shutil.which("ranlib")
        return env


recipe = NumpyRecipe()
