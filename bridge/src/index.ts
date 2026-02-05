#!/usr/bin/env node
/**
 * nanobot WhatsApp Bridge
 * 
 * 此桥接器连接 WhatsApp Web 和 nanobot 的 Python 后端，
 * 通过 WebSocket 进行通信。
 * 
 * 功能：
 * - WhatsApp Web 认证
 * - 消息转发（WhatsApp ↔ nanobot）
 * - 自动重连逻辑
 * 
 * 使用方法：
 *   npm run build && npm start
 *   
 * 或使用自定义设置：
 *   BRIDGE_PORT=3001 AUTH_DIR=~/.nanobot/whatsapp npm start
 */

// 为 Baileys 库提供 crypto polyfill（ESM 环境需要）
import { webcrypto } from 'crypto';
if (!globalThis.crypto) {
  (globalThis as any).crypto = webcrypto;
}

import { BridgeServer } from './server.js';
import { homedir } from 'os';
import { join } from 'path';

// 服务端口（默认 3001）
const PORT = parseInt(process.env.BRIDGE_PORT || '3001', 10);
// 认证数据存储目录
const AUTH_DIR = process.env.AUTH_DIR || join(homedir(), '.nanobot', 'whatsapp-auth');

console.log('🐈 nanobot WhatsApp Bridge');
console.log('========================\n');

// 创建并启动桥接服务器
const server = new BridgeServer(PORT, AUTH_DIR);

// 优雅关闭处理
process.on('SIGINT', async () => {
  console.log('\n\n正在关闭...');
  await server.stop();
  process.exit(0);
});

process.on('SIGTERM', async () => {
  await server.stop();
  process.exit(0);
});

// 启动服务器
server.start().catch((error) => {
  console.error('启动桥接器失败:', error);
  process.exit(1);
});
