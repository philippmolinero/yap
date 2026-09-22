// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "Yap",
    platforms: [.macOS(.v15)],
    targets: [
        .target(
            name: "YapCore",
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
        .executableTarget(
            name: "Yap",
            dependencies: ["YapCore"],
            resources: [
                .copy("Resources/icon_menubar.png"),
                .copy("Resources/record_start.wav"),
                .copy("Resources/record_stop.wav"),
                .copy("Resources/ui_click.wav"),
                .copy("Resources/default.toml"),
                .copy("Resources/vocabulary.txt"),
            ],
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
        .executableTarget(
            name: "YapCoreTests",
            dependencies: ["YapCore"],
            swiftSettings: [.swiftLanguageMode(.v6)]
        ),
    ]
)
