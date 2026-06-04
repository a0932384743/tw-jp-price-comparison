module.exports = {
  extends: ['expo'],
  rules: {
    // ── Correctness ───────────────────────────────────────────────────────────
    'no-console': ['warn', { allow: ['warn', 'error'] }],
    'no-debugger': 'error',
    'no-duplicate-imports': 'error',
    'no-var': 'error',
    'prefer-const': 'error',
    'eqeqeq': ['error', 'always', { null: 'ignore' }],

    // ── TypeScript ────────────────────────────────────────────────────────────
    '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    '@typescript-eslint/no-explicit-any': 'warn',

    // ── React hooks ───────────────────────────────────────────────────────────
    'react-hooks/exhaustive-deps': 'warn',

    // ── Coding style ─────────────────────────────────────────────────────────
    'object-shorthand': ['warn', 'always'],
    'prefer-template': 'warn',
    'arrow-body-style': ['warn', 'as-needed'],
  },
  ignorePatterns: [
    'node_modules/',
    'dist/',
    '.expo/',
    'coverage/',
    'babel.config.js',
  ],
  overrides: [
    {
      // Test and setup files use require() and matcher expressions freely
      files: ['**/__tests__/**/*', '**/*.test.*', 'jest.setup.*'],
      rules: {
        '@typescript-eslint/no-require-imports': 'off',
        'no-unused-expressions': 'off',
      },
    },
  ],
};
