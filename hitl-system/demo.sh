#!/bin/bash

# demo.sh: PoC Test Script for Forum Moderation Workflow
# Run: chmod +x demo.sh && ./demo.sh
# Watches FastAPI/Dramatiq logs in other terminals for events.

set -e  # Exit on error

BASE_URL="http://localhost:8000"
echo "=== Starting PoC Demo: Forum Moderation with Rollback ==="
echo "Ensure FastAPI (port 8000) and Dramatiq worker are running!"
read -p "Press Enter to continue..."

# Helper: Extract thread_id from JSON response (no jq needed)
extract_thread_id() {
    local response=$(cat)  # Pipe input
    echo "$response" | sed -n 's/.*"thread_id": "\([^"]*\)".*/\1/p' || echo "manual_copy_needed"
}

# Step 1: Start workflow (violating content → triggers AI pause)
echo "Step 1: Starting workflow..."
START_RESPONSE=$(curl -s -X POST "$BASE_URL/workflows/start" \
    -H "Content-Type: application/json" \
    -d '{
      "content_id": "post_123",
      "content_text": "Help! My API key sk_live_abc123 isn'\''t working in Citadel-Internal project."
    }')

THREAD_ID=$(echo "$START_RESPONSE" | extract_thread_id)
if [[ "$THREAD_ID" == "manual_copy_needed" ]]; then
    echo "$START_RESPONSE"  # Show raw JSON
    read -p "Copy THREAD_ID (e.g., moderation_case_xxx) and paste here: " THREAD_ID
fi

echo "Thread ID: $THREAD_ID"
echo "Expected: Workflow started. Check logs for AI analysis → pause."

# Step 2: Poll status (paused state)
echo "Step 2: Polling status (wait for background task ~5s)..."
sleep 5
STATUS=$(curl -s "$BASE_URL/workflows/status/$THREAD_ID")
echo "Status: $STATUS"
echo "Expected: ai_suggestion='confidential_info', status='interrupted', human_decision=null"

# Step 3: Resume with decision
echo "Step 3: Resuming with 'remove_content_and_ban'..."
curl -s -X POST "$BASE_URL/workflows/$THREAD_ID/resume" \
    -H "Content-Type: application/json" \
    -d '{
      "human_decision": "remove_content_and_ban",
      "moderator_id": "mod_user_42",
      "comment": "API key exposed"
    }' > /dev/null  # Silent, watch worker logs
echo "Expected: Decision received. Check Dramatiq logs for resume → action."

# Step 4: Poll post-action
echo "Step 4: Polling final status (wait ~3s)..."
sleep 3
STATUS=$(curl -s "$BASE_URL/workflows/status/$THREAD_ID")
echo "Status: $STATUS"
echo "Expected: human_decision='remove_content_and_ban', status='done'"

# Step 5: Trigger rollback
echo "Step 5: Rolling back..."
curl -s -X POST "$BASE_URL/workflows/$THREAD_ID/rollback" \
    -H "Content-Type: application/json" \
    -d '{"reason": "Post clarification: fake key for tutorial"}' > /dev/null
echo "Expected: Rollback initiated. Check logs for 'ROLLING BACK' → re-pause."

# Step 6: Poll after rollback
echo "Step 6: Polling after rollback..."
STATUS=$(curl -s "$BASE_URL/workflows/status/$THREAD_ID")
echo "Status: $STATUS"
echo "Expected: human_decision=null, status='interrupted', escalation_count=1"

# Step 7: Re-resume (escalated review)
echo "Step 7: Re-resuming with 'ignore'..."
curl -s -X POST "$BASE_URL/workflows/$THREAD_ID/resume" \
    -H "Content-Type: application/json" \
    -d '{
      "human_decision": "ignore",
      "moderator_id": "mod_user_42",
      "comment": "Cleared after review"
    }' > /dev/null

# Step 8: Final poll
echo "Step 8: Final status (wait ~3s)..."
sleep 3
STATUS=$(curl -s "$BASE_URL/workflows/status/$THREAD_ID")
echo "Status: $STATUS"
echo "Expected: human_decision='ignore', status='done', escalation_count=1"

echo "=== Demo Complete! Check Postgres for checkpoints if needed. ==="
echo "To test edges: Rerun script for new thread, or tweak content_text for non-escalate."