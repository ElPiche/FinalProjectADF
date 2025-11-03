# KB-MCP - Knowledge Base Model Context Protocol Server

## ⚠️ CRITICAL: Docker-Only Deployment

**KB-MCP MUST run in Docker containers.** Direct execution on the host machine is not supported and will violate architectural requirements.

### Why Docker?
- **Network Isolation**: Proper container-to-container communication
- **Service Dependencies**: MongoDB and Elasticsearch connectivity
- **MCP Integration**: Designed for Docker exec commands in `.kilocode/mcp.json`
- **Production Ready**: Containerized deployment with health checks

### 🚀 Quick Start

1. **Start Services**:
   ```bash
   docker-compose up -d mongodb elasticsearch-dataset kb-mcp
   ```

2. **Verify Health**:
   ```bash
   docker-compose ps
   docker logs kb-mcp
   ```

3. **MCP Integration**: The `.kilocode/mcp.json` is pre-configured for Docker exec.

### 🧪 Testing (Inside Container)

```bash
# Unit tests
docker exec kb-mcp python -m tests.test_models
docker exec kb-mcp python -m tests.test_validation

# Smoke tests
docker exec kb-mcp python smoke_test.py

# Profiling
docker exec kb-mcp python profile_after.py
```

### 📁 Architecture

- **Modular Design**: Split from monolithic 1900-line script
- **Timeout Protection**: 2-5 second timeouts prevent hangs
- **Instrumentation**: Performance monitoring decorators
- **MCP Tools**: 6 fully functional anomaly detection tools

### 🛠️ Development

- **No Direct Execution**: Never run `python kb-mcp.py` on host
- **Container First**: All development and testing in Docker
- **MCP Client**: Use VS Code MCP integration for tool testing

### 📋 Available Tools

1. `create_da_config` - Create anomaly detection configurations
2. `modify_kb_config` - Update existing configurations
3. `list_kb_configurations` - List all configurations
4. `describe_mcp_server` - Server documentation
5. `list_available_algorithms` - Algorithm specifications
6. `elasticsearch_sql` - SQL query execution

### 🔧 Configuration

- **MongoDB**: `mongodb://admin:1q2w3E*@mongodb:27017/?authSource=admin&replicaSet=rs0`
- **Elasticsearch**: `http://elasticsearch-dataset:9200`
- **MCP Transport**: stdio (via Docker exec)

---

**Remember**: Docker execution is mandatory for proper functionality and MCP integration.