#!/bin/bash
set -e

# Write the current index to a tree object
TREE=$(git write-tree)

# Create a commit object using the tree
COMMIT=$(echo "Fix AI SDK versions and Gemini API key" | env GIT_AUTHOR_NAME="Emmanuel" GIT_AUTHOR_EMAIL="emmanuel@example.com" GIT_COMMITTER_NAME="Emmanuel" GIT_COMMITTER_EMAIL="emmanuel@example.com" git commit-tree $TREE -p HEAD)

# Update the main branch to point to this new commit
git update-ref refs/heads/main $COMMIT

# Point HEAD to the main branch
git symbolic-ref HEAD refs/heads/main

echo "Commit created successfully: $COMMIT"
git status
