// swift-tools-version:5.9
import PackageDescription

let rb = "/opt/homebrew/opt/rubberband", sr = "/opt/homebrew/opt/libsamplerate"
let package = Package(
    name: "RehearsalPlayer",
    platforms: [.macOS(.v13)],
    targets: [
        .target(name: "CEngine",
                exclude: ["third_party"],
                cxxSettings: [.unsafeFlags(["-I\(rb)/include", "-ISources/CEngine/third_party", "-O3"])],
                linkerSettings: [.unsafeFlags(["\(rb)/lib/librubberband.a", "\(sr)/lib/libsamplerate.a"]),
                                 .linkedFramework("Accelerate"), .linkedFramework("AudioToolbox"), .linkedFramework("CoreAudio")]),
        .executableTarget(name: "RehearsalPlayer", dependencies: ["CEngine"]),
        .executableTarget(name: "enginetest", dependencies: ["CEngine"]),
    ],
    cxxLanguageStandard: .cxx20
)
