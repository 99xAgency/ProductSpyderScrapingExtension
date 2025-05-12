const path = require("path")
const CopyPlugin = require("copy-webpack-plugin")

module.exports = {
  mode: "production",
  devtool: "source-map",
  entry: {
    background: "./src/background.ts",
    popup: "./src/popup.ts",
    content: "./src/content.ts",
  },
  output: {
    path: path.resolve(__dirname, "dist"),
    filename: "[name].js",
  },
  optimization: {
    minimize: true,
  },
  module: {
    rules: [
      {
        test: /\.ts$/,
        use: "ts-loader",
        exclude: /node_modules/,
      },
    ],
  },
  resolve: {
    extensions: [".ts", ".js"],
  },
  plugins: [
    new CopyPlugin({
      patterns: [
        { from: "manifest.json", to: "manifest.json" },
        { from: "src/popup.html", to: "." },
        // { from: "src/icons", to: "icons" },
      ],
    }),
  ],
}
