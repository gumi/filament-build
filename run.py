import argparse
import logging
import os
import platform
import shutil
import subprocess
import tarfile
from typing import Dict, List, Optional

logging.basicConfig(level=logging.INFO)


class ChangeDirectory:
    def __init__(self, cwd):
        self._cwd = cwd

    def __enter__(self):
        self._old_cwd = os.getcwd()
        logging.debug(f"pushd {self._old_cwd} --> {self._cwd}")
        os.chdir(self._cwd)

    def __exit__(self, exctype, excvalue, trace):
        logging.debug(f"popd {self._old_cwd} <-- {self._cwd}")
        os.chdir(self._old_cwd)
        return False


def cd(cwd):
    return ChangeDirectory(cwd)


def cmd(args, **kwargs):
    logging.debug(f"+{args} {kwargs}")
    if "check" not in kwargs:
        kwargs["check"] = True
    if "resolve" in kwargs:
        resolve = kwargs["resolve"]
        del kwargs["resolve"]
    else:
        resolve = True
    if resolve:
        args = [shutil.which(args[0]), *args[1:]]
    return subprocess.run(args, **kwargs)


def cmdcap(args, **kwargs):
    kwargs["stdout"] = subprocess.PIPE
    kwargs["stderr"] = subprocess.PIPE
    kwargs["encoding"] = "utf-8"
    return cmd(args, **kwargs).stdout.strip()


def rm_rf(path: str):
    if not os.path.exists(path):
        return
    if os.path.isfile(path) or os.path.islink(path):
        os.remove(path)
    if os.path.isdir(path):
        shutil.rmtree(path)


def mkdir_p(path: str):
    os.makedirs(path, exist_ok=True)


def read_version_file(path: str) -> Dict[str, str]:
    versions = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            versions[key.strip()] = value.strip().strip('"')
    return versions


def enum_all_files(dir, dir2):
    for root, _, files in os.walk(dir):
        for file in files:
            yield os.path.relpath(os.path.join(root, file), dir2)


# ターゲット定義
TARGETS = [
    "macos_arm64",
    "ios_device_arm64",
    "ios_simulator_arm64",
    "android_arm64_v8a",
    "windows_x64",
    "web_wasm",
]

# ホストツール (iOS/Android ビルドの前提条件)
MOBILE_HOST_TOOLS = "matc resgen cmgen filamesh uberz"

# ホストツール (Web ビルドの前提条件)
WEB_HOST_TOOLS = "matc resgen cmgen filamesh uberz mipgen"

# ターゲット別パッチ定義
# 全ターゲット共通のパッチはここに追加する
PATCHES: Dict[str, List[str]] = {
    "macos_arm64": [],
    "ios_device_arm64": [],
    "ios_simulator_arm64": [],
    "android_arm64_v8a": [],
    "windows_x64": [],
    "web_wasm": [],
}


def check_target(target: str) -> bool:
    """現在の OS でビルド可能なターゲットかどうかを確認する"""
    system = platform.system()
    if system == "Darwin":
        return target in ("macos_arm64", "ios_device_arm64", "ios_simulator_arm64")
    elif system == "Linux":
        return target in ("android_arm64_v8a", "web_wasm")
    elif system == "Windows":
        return target in ("windows_x64",)
    return False


def get_filament_source(source_dir: str, version: str):
    """Filament ソースを clone して指定バージョンに checkout する"""
    filament_dir = os.path.join(source_dir, "filament")
    if not os.path.exists(filament_dir):
        logging.info(f"Cloning Filament into {filament_dir}...")
        cmd([
            "git", "clone", "--depth", "1",
            "--branch", f"v{version}",
            "https://github.com/google/filament.git",
            filament_dir,
        ])
    else:
        logging.info(f"Filament source already exists at {filament_dir}")
        with cd(filament_dir):
            cmd(["git", "fetch", "--tags", "--depth", "1", "origin",
                 f"refs/tags/v{version}:refs/tags/v{version}"],
                check=False)
            cmd(["git", "checkout", f"v{version}"])

    return filament_dir


def apply_patch(patch: str, dir: str):
    with cd(dir):
        logging.info(f"Applying patch: {os.path.basename(patch)}")
        cmd(["git", "apply", patch])


def apply_patches(target: str, patch_dir: str, src_dir: str):
    patches = PATCHES.get(target, [])
    for patch in patches:
        patch_path = os.path.join(patch_dir, patch)
        apply_patch(patch_path, src_dir)
    if patches:
        logging.info(f"Applied {len(patches)} patch(es).")
    else:
        logging.info("No patches to apply.")


def reset_source(src_dir: str):
    """ソースをクリーンな状態に戻す"""
    with cd(src_dir):
        cmd(["git", "checkout", "--", "."])
        cmd(["git", "clean", "-df"])


def build_filament_macos(filament_dir: str, build_dir: str):
    """macOS arm64 向け Filament をビルドする"""
    logging.info("=== Building Filament for macos_arm64 ===")
    with cd(filament_dir):
        cmd([
            "./build.sh", "-i", "-p", "desktop", "release",
        ])


def build_filament_ios_device(filament_dir: str, build_dir: str):
    """iOS device arm64 向け Filament をビルドする"""
    logging.info("=== Building Filament for ios_device_arm64 ===")
    with cd(filament_dir):
        cmd([
            "./build.sh", "-i", "-p", "ios", "release",
        ])


def build_filament_ios_simulator(filament_dir: str, build_dir: str):
    """iOS simulator arm64 向け Filament をビルドする (独自 CMake 呼び出し)"""
    logging.info("=== Building Filament for ios_simulator_arm64 ===")

    with cd(filament_dir):
        # ホストツールをビルドする (公式 build.sh と同じ構成)
        # -DIMPORT_EXECUTABLES_DIR を渡すことで ImportExecutables-Release.cmake が生成される
        logging.info("Building host tools...")
        host_build_dir = os.path.join(filament_dir, "out", "cmake-release")
        mkdir_p(host_build_dir)
        with cd(host_build_dir):
            cmd([
                "cmake", "-G", "Ninja",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_INSTALL_PREFIX=../release/filament",
                "-DIMPORT_EXECUTABLES_DIR=out/cmake-release",
                "../..",
            ])
            cmd(["ninja", *MOBILE_HOST_TOOLS.split()])

        # iOS simulator arm64 をビルドする
        logging.info("Building iOS simulator arm64...")
        sim_build_dir = os.path.join(filament_dir, "out", "cmake-ios-sim-release-arm64")
        mkdir_p(sim_build_dir)
        with cd(sim_build_dir):
            cmd([
                "cmake", "-G", "Ninja",
                "-DIMPORT_EXECUTABLES_DIR=out/cmake-release",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_INSTALL_PREFIX=../ios-release/filament",
                '-DIOS_ARCH=arm64',
                '-DPLATFORM_NAME=iphonesimulator',
                "-DIOS=1",
                "-DCMAKE_TOOLCHAIN_FILE=../../third_party/clang/iOS.cmake",
                "-DFILAMENT_SKIP_SAMPLES=ON",
                "../..",
            ])
            cmd(["ninja"])
            cmd(["ninja", "install"])


def build_filament_android(filament_dir: str, build_dir: str):
    """Android arm64-v8a 向け Filament をビルドする"""
    logging.info("=== Building Filament for android_arm64_v8a ===")

    if not os.environ.get("ANDROID_HOME"):
        raise Exception("ANDROID_HOME is not set")

    with cd(filament_dir):
        # ホスト���ールをビルド���る (Android ビルドの前提条���)
        logging.info("Building host tools...")
        host_build_dir = os.path.join(filament_dir, "out", "cmake-release")
        mkdir_p(host_build_dir)
        with cd(host_build_dir):
            cmd([
                "cmake", "-G", "Ninja",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_INSTALL_PREFIX=../release/filament",
                "-DIMPORT_EXECUTABLES_DIR=out/cmake-release",
                "../..",
            ])
            cmd(["ninja", *MOBILE_HOST_TOOLS.split()])

        # Android arm64-v8a をビルドする
        logging.info("Building Android arm64-v8a...")
        android_build_dir = os.path.join(filament_dir, "out", "cmake-android-release-aarch64")
        mkdir_p(android_build_dir)
        with cd(android_build_dir):
            cmd([
                "cmake", "-G", "Ninja",
                "-DIMPORT_EXECUTABLES_DIR=out/cmake-release",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_INSTALL_PREFIX=../android-release/filament",
                "-DCMAKE_TOOLCHAIN_FILE=../../build/toolchain-aarch64-linux-android.cmake",
                "-DFILAMENT_SKIP_SAMPLES=ON",
                "../..",
            ])
            cmd(["ninja"])
            cmd(["ninja", "install"])


def build_filament_windows(filament_dir: str, build_dir: str):
    """Windows x64 向け Filament をビルドする"""
    logging.info("=== Building Filament for windows_x64 ===")
    with cd(filament_dir):
        win_build_dir = os.path.join(filament_dir, "out", "cmake-release")
        mkdir_p(win_build_dir)
        with cd(win_build_dir):
            cmd([
                "cmake", "-G", "Ninja",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_INSTALL_PREFIX=../release/filament",
                "-DUSE_STATIC_CRT=ON",
                "-DFILAMENT_SUPPORTS_VULKAN=ON",
                "-DFILAMENT_SKIP_SAMPLES=ON",
                "-DFILAMENT_WINDOWS_CI_BUILD=ON",
                "../..",
            ])
            cmd(["ninja"])
            cmd(["ninja", "install"])


def build_filament_web(filament_dir: str, build_dir: str):
    """Web (WebAssembly) 向け Filament をビルドする"""
    logging.info("=== Building Filament for web_wasm ===")

    emsdk = os.environ.get("EMSDK")
    if not emsdk:
        raise Exception("EMSDK is not set")

    with cd(filament_dir):
        # ホストツールをビルドする (Web ビルドの前提条件)
        logging.info("Building host tools...")
        host_build_dir = os.path.join(filament_dir, "out", "cmake-release")
        mkdir_p(host_build_dir)
        with cd(host_build_dir):
            cmd([
                "cmake", "-G", "Ninja",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_INSTALL_PREFIX=../release/filament",
                "-DIMPORT_EXECUTABLES_DIR=out/cmake-release",
                "-DFILAMENT_SKIP_SAMPLES=ON",
                "../..",
            ])
            cmd(["ninja", *WEB_HOST_TOOLS.split()])

        # WebGL をビルドする
        logging.info("Building WebGL...")
        toolchain = os.path.join(
            emsdk, "upstream", "emscripten",
            "cmake", "Modules", "Platform", "Emscripten.cmake",
        )
        web_build_dir = os.path.join(filament_dir, "out", "cmake-webgl-release")
        mkdir_p(web_build_dir)
        with cd(web_build_dir):
            cmd([
                "cmake", "-G", "Ninja",
                "-DIMPORT_EXECUTABLES_DIR=out/cmake-release",
                "-DCMAKE_BUILD_TYPE=Release",
                "-DCMAKE_INSTALL_PREFIX=../webgl-release/filament",
                f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
                "-DWEBGL=1",
                "../..",
            ])
            cmd(["ninja"])


# ターゲットごとのビルド成果物のインストールディレクトリ
INSTALL_DIRS = {
    "macos_arm64": os.path.join("out", "release", "filament"),
    "ios_device_arm64": os.path.join("out", "ios-release", "filament"),
    "ios_simulator_arm64": os.path.join("out", "ios-release", "filament"),
    "android_arm64_v8a": os.path.join("out", "android-release", "filament"),
    "windows_x64": os.path.join("out", "release", "filament"),
    "web_wasm": os.path.join("out", "cmake-webgl-release", "web", "filament-js"),
}

# ターゲットごとのビルド関数
BUILD_FUNCS = {
    "macos_arm64": build_filament_macos,
    "ios_device_arm64": build_filament_ios_device,
    "ios_simulator_arm64": build_filament_ios_simulator,
    "android_arm64_v8a": build_filament_android,
    "windows_x64": build_filament_windows,
    "web_wasm": build_filament_web,
}


def copy_headers(install_dir: str, package_dir: str):
    """ヘッダーファイルをパッケージディレクトリにコピーする"""
    src = os.path.join(install_dir, "include")
    dst = os.path.join(package_dir, "include")
    if os.path.exists(src):
        shutil.copytree(src, dst)


def copy_libraries(install_dir: str, package_dir: str):
    """ライブラリファイルをパッケージディレクトリにコピーする"""
    lib_dir = os.path.join(package_dir, "lib")
    mkdir_p(lib_dir)
    src_lib = os.path.join(install_dir, "lib")
    if os.path.exists(src_lib):
        for root, _, files in os.walk(src_lib):
            for f in files:
                if f.endswith(".a") or f.endswith(".lib"):
                    shutil.copy2(os.path.join(root, f), lib_dir)


def copy_licenses(filament_dir: str, package_dir: str, base_dir: str):
    """ライセンスファイルをパッケージディレクトリにコピーする"""
    license_src = os.path.join(filament_dir, "LICENSE")
    if not os.path.exists(license_src):
        raise Exception(f"LICENSE not found: {license_src}")
    shutil.copy2(license_src, os.path.join(package_dir, "LICENSE"))

    third_party = os.path.join(base_dir, "NOTICE")
    if not os.path.exists(third_party):
        raise Exception(f"NOTICE not found: {third_party}")
    shutil.copy2(third_party, os.path.join(package_dir, "NOTICE"))


def generate_version_info(package_dir: str, version_file_path: str):
    """バージョン情報をパッケージに含める"""
    shutil.copyfile(version_file_path, os.path.join(package_dir, "VERSIONS"))


def verify_artifacts(target: str, package_dir: str):
    """成果物の検証を行う"""
    lib_dir = os.path.join(package_dir, "lib")

    if target in ("ios_device_arm64", "ios_simulator_arm64"):
        sample_lib = None
        for f in os.listdir(lib_dir):
            if f == "libfilament.a":
                sample_lib = os.path.join(lib_dir, f)
                break

        if sample_lib and platform.system() == "Darwin":
            result = cmdcap(["otool", "-l", sample_lib], check=False)
            if target == "ios_simulator_arm64":
                if "platform 7" in result:
                    logging.info("OK: platform is iossim (7)")
                else:
                    logging.warning("WARNING: expected platform iossim (7)")
            elif target == "ios_device_arm64":
                if "platform 2" in result:
                    logging.info("OK: platform is ios (2)")
                else:
                    logging.warning("WARNING: expected platform ios (2)")

    if target == "android_arm64_v8a":
        if os.path.exists(os.path.join(lib_dir, "libgltfio_core.a")):
            logging.info("OK: libgltfio_core.a found")
        else:
            logging.warning("WARNING: libgltfio_core.a not found")

    if target == "windows_x64":
        if os.path.exists(os.path.join(lib_dir, "filament.lib")):
            logging.info("OK: filament.lib found")
        else:
            logging.warning("WARNING: filament.lib not found")


def copy_web_artifacts(install_dir: str, package_dir: str):
    """Web ビルドの成果物 (JS/WASM) をコピーする"""
    for root, _, files in os.walk(install_dir):
        for f in files:
            if f.endswith(".js") or f.endswith(".wasm") or f.endswith(".d.ts"):
                shutil.copy2(os.path.join(root, f), package_dir)


def package_filament(
    source_dir: str,
    build_dir: str,
    package_dir: str,
    target: str,
    base_dir: str,
):
    """ビルド成果物をパッケージングする"""
    filament_dir = os.path.join(source_dir, "filament")
    install_dir = os.path.join(filament_dir, INSTALL_DIRS[target])

    filament_package_dir = os.path.join(package_dir, "filament")
    rm_rf(filament_package_dir)
    mkdir_p(filament_package_dir)

    if target == "web_wasm":
        # Web は JS/WASM をパッケージングする
        copy_web_artifacts(install_dir, filament_package_dir)
    else:
        # ライブラリをコピーする
        copy_libraries(install_dir, filament_package_dir)

        # ヘッダーをコピーする
        copy_headers(install_dir, filament_package_dir)

        # 成果物を検証する
        verify_artifacts(target, filament_package_dir)

    # ライセンスをコピーする
    copy_licenses(filament_dir, filament_package_dir, base_dir)

    # バージョン情報をコピーする
    generate_version_info(filament_package_dir, os.path.join(base_dir, "VERSION"))

    # tar.gz にパッケージングする
    version = read_version_file(os.path.join(base_dir, "VERSION"))
    filament_version = version["FILAMENT_VERSION"]
    archive_name = f"filament-v{filament_version}-{target}.tar.gz"
    with cd(package_dir):
        with tarfile.open(archive_name, "w:gz") as tar:
            for file in enum_all_files("filament", "."):
                tar.add(name=file, arcname=file)

    logging.info(f"Package created: {os.path.join(package_dir, archive_name)}")


BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def main():
    parser = argparse.ArgumentParser(description="Filament マルチプラットフォームビルドツール")
    sp = parser.add_subparsers()

    # build サブコマンド
    bp = sp.add_parser("build", help="Filament をビルドする")
    bp.set_defaults(op="build")
    bp.add_argument("target", choices=TARGETS)
    bp.add_argument("--source-dir", help="ソースディレクトリ")
    bp.add_argument("--build-dir", help="ビルドディレクトリ")

    # package サブコマンド
    pp = sp.add_parser("package", help="ビルド成果物をパッケージングする")
    pp.set_defaults(op="package")
    pp.add_argument("target", choices=TARGETS)
    pp.add_argument("--source-dir", help="ソースディレクトリ")
    pp.add_argument("--build-dir", help="ビルドディレクトリ")
    pp.add_argument("--package-dir", help="パッケージ出力ディレクトリ")

    args = parser.parse_args()

    if not hasattr(args, "op"):
        parser.error("Required subcommand")

    if not check_target(args.target):
        raise Exception(f"Target {args.target} is not supported on {platform.system()}")

    version = read_version_file(os.path.join(BASE_DIR, "VERSION"))
    filament_version = version["FILAMENT_VERSION"]
    filament_commit = version.get("FILAMENT_COMMIT", "")

    source_dir = os.path.join(BASE_DIR, "_source", args.target)
    build_dir = os.path.join(BASE_DIR, "_build", args.target, "release")
    package_dir = os.path.join(BASE_DIR, "_package", args.target)
    patch_dir = os.path.join(BASE_DIR, "patches")

    if args.source_dir is not None:
        source_dir = os.path.abspath(args.source_dir)
    if args.build_dir is not None:
        build_dir = os.path.abspath(args.build_dir)

    if args.op == "build":
        mkdir_p(source_dir)
        mkdir_p(build_dir)

        with cd(BASE_DIR):
            # ソース取得
            filament_dir = get_filament_source(source_dir, filament_version)

            # パッチ適用
            apply_patches(args.target, patch_dir, filament_dir)

            # ビルド
            build_func = BUILD_FUNCS[args.target]
            build_func(filament_dir, build_dir)

    if args.op == "package":
        if args.package_dir is not None:
            package_dir = os.path.abspath(args.package_dir)

        mkdir_p(package_dir)

        with cd(BASE_DIR):
            package_filament(
                source_dir=source_dir,
                build_dir=build_dir,
                package_dir=package_dir,
                target=args.target,
                base_dir=BASE_DIR,
            )


if __name__ == "__main__":
    main()
