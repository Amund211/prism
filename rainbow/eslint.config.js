import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";
import reactCompiler from "eslint-plugin-react-compiler";
import react from "eslint-plugin-react";
import pluginQuery from "@tanstack/eslint-plugin-query";

export default tseslint.config(
    { ignores: ["dist", "src/routeTree.gen.ts"] },
    {
        settings: { react: { version: "detect" } },
        extends: [
            js.configs.recommended,
            ...tseslint.configs.strictTypeChecked,
            ...tseslint.configs.stylisticTypeChecked,
        ],
        files: ["**/*.{ts,tsx}"],
        languageOptions: {
            ecmaVersion: 2020,
            globals: globals.browser,
        },
        plugins: {
            "react-hooks": reactHooks,
            "react-refresh": reactRefresh,
            "react-compiler": reactCompiler,
            react: react,
            "@tanstack/query": pluginQuery,
        },
        rules: {
            ...reactHooks.configs.recommended.rules,
            ...react.configs.recommended.rules,
            ...react.configs["jsx-runtime"].rules,
            "react-compiler/react-compiler": "error",
            "react-refresh/only-export-components": [
                "warn",
                { allowConstantExport: true },
            ],
            "react/prop-types": "off",
        },
        languageOptions: {
            parserOptions: {
                project: ["./tsconfig.node.json", "./tsconfig.app.json"],
                tsconfigRootDir: import.meta.dirname,
            },
        },
    },
    ...pluginQuery.configs["flat/recommended"],
);
