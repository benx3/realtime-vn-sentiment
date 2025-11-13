#!/bin/bash
# MongoDB Replica Set Initialization Script
# This script ensures MongoDB replica set is initialized on container startup

MONGO_HOST="${MONGO_HOST:-mongo:27017}"

echo "⏳ Waiting for MongoDB to be ready at $MONGO_HOST..."
MAX_WAIT=30
COUNTER=0
until mongosh --host $MONGO_HOST --quiet --eval "db.adminCommand('ping')" > /dev/null 2>&1; do
  sleep 2
  COUNTER=$((COUNTER+1))
  echo "  Attempt $COUNTER/$MAX_WAIT..."
  if [ $COUNTER -gt $MAX_WAIT ]; then
    echo "❌ MongoDB not ready after $((MAX_WAIT*2)) seconds"
    exit 1
  fi
done

echo "🔍 Checking replica set status..."
RS_STATUS=$(mongosh --host $MONGO_HOST --quiet --eval "rs.status().ok" 2>&1)

if [[ "$RS_STATUS" != "1" ]]; then
  echo "🚀 Initializing replica set 'rs0'..."
  mongosh --host $MONGO_HOST --eval "rs.initiate()"
  
  echo "⏳ Waiting for PRIMARY election..."
  COUNTER=0
  MAX_WAIT_PRIMARY=15
  until mongosh --host $MONGO_HOST --quiet --eval "rs.isMaster().ismaster" 2>/dev/null | grep -q "true"; do
    sleep 2
    COUNTER=$((COUNTER+1))
    if [ $COUNTER -gt $MAX_WAIT_PRIMARY ]; then
      echo "⚠️ PRIMARY not elected after $((MAX_WAIT_PRIMARY*2)) seconds, but continuing..."
      break
    fi
  done
  
  echo "✅ Replica set initialized successfully!"
else
  echo "✅ Replica set already initialized!"
fi

echo "📊 Current replica set status:"
mongosh --host $MONGO_HOST --quiet --eval "rs.isMaster().ismaster"
