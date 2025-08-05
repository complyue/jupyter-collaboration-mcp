#!/bin/bash

# Script to set up Git hooks for auto-formatting

# Get the absolute path of the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOKS_DIR="$SCRIPT_DIR/git-hooks"

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Error: Not in a git repository."
    exit 1
fi

# Get the git hooks directory
GIT_DIR=$(git rev-parse --git-dir)
GIT_HOOKS_DIR="$GIT_DIR/hooks"

# Create a symlink for the pre-commit hook
echo "Setting up pre-commit hook..."
ln -sf "$HOOKS_DIR/pre-commit" "$GIT_HOOKS_DIR/pre-commit"

echo "Git hooks have been set up successfully!"
echo "The pre-commit hook will automatically format your Python files with black and isort before each commit."