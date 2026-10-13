这里放翻前求解器输出的 `2max.bin` 到 `6max.bin`，打包时会作为资源装进安装包。

本地开发：在仓库根目录运行 `cargo run --release -p preflop --bin solve -- <人数>`，
再把 `data/preflop/<人数>max.bin` 复制过来。没有这些文件时，应用的翻后两人底池会退回规则近似。
CI 会自动生成并缓存它们。
