/**
 * WebSocket 服务器模块
 * 
 * 实现 Python 后端与 Node.js 桥接器之间的 WebSocket 通信。
 * 
 * 架构：
 * - WebSocketServer: 监听 Python 客户端连接
 * - WhatsAppClient: WhatsApp Web 客户端
 * - 消息广播: 将 WhatsApp 消息广播给所有连接的 Python 客户端
 * 
 * 消息流程：
 * 1. WhatsApp 收到消息 → broadcast() → Python 客户端
 * 2. Python 发送命令 → handleCommand() → WhatsApp 发送消息
 */

import { WebSocketServer, WebSocket } from 'ws';
import { WhatsAppClient, InboundMessage } from './whatsapp.js';

/** 发送命令接口 */
interface SendCommand {
  type: 'send';
  to: string;      // 目标手机号或群组 ID
  text: string;    // 消息内容
}

/** 桥接器消息接口 */
interface BridgeMessage {
  type: 'message' | 'status' | 'qr' | 'error';
  [key: string]: unknown;
}

/**
 * 桥接服务器类
 * 
 * 管理 WebSocket 服务器和 WhatsApp 客户端，
 * 实现 Python 后端与 WhatsApp 之间的双向通信。
 */
export class BridgeServer {
  private wss: WebSocketServer | null = null;      // WebSocket 服务器实例
  private wa: WhatsAppClient | null = null;        // WhatsApp 客户端实例
  private clients: Set<WebSocket> = new Set();     // 已连接的 Python 客户端

  /**
   * 创建桥接服务器实例
   * 
   * @param port - WebSocket 监听端口
   * @param authDir - WhatsApp 认证数据存储目录
   */
  constructor(private port: number, private authDir: string) {}

  /**
   * 启动桥接服务器
   * 
   * 初始化流程：
   * 1. 创建 WebSocket 服务器
   * 2. 初始化 WhatsApp 客户端
   * 3. 设置事件处理器
   * 4. 连接 WhatsApp
   */
  async start(): Promise<void> {
    // 创建 WebSocket 服务器
    this.wss = new WebSocketServer({ port: this.port });
    console.log(`🌉 Bridge server listening on ws://localhost:${this.port}`);

    // 初始化 WhatsApp 客户端
    this.wa = new WhatsAppClient({
      authDir: this.authDir,
      // 收到消息时广播给所有 Python 客户端
      onMessage: (msg) => this.broadcast({ type: 'message', ...msg }),
      // 显示二维码时广播
      onQR: (qr) => this.broadcast({ type: 'qr', qr }),
      // 状态变化时广播
      onStatus: (status) => this.broadcast({ type: 'status', status }),
    });

    // 处理 WebSocket 连接
    this.wss.on('connection', (ws) => {
      console.log('🔗 Python client connected');
      this.clients.add(ws);

      // 处理来自 Python 的消息
      ws.on('message', async (data) => {
        try {
          const cmd = JSON.parse(data.toString()) as SendCommand;
          await this.handleCommand(cmd);
          ws.send(JSON.stringify({ type: 'sent', to: cmd.to }));
        } catch (error) {
          console.error('Error handling command:', error);
          ws.send(JSON.stringify({ type: 'error', error: String(error) }));
        }
      });

      // 客户端断开连接
      ws.on('close', () => {
        console.log('🔌 Python client disconnected');
        this.clients.delete(ws);
      });

      // 连接错误
      ws.on('error', (error) => {
        console.error('WebSocket error:', error);
        this.clients.delete(ws);
      });
    });

    // 连接 WhatsApp
    await this.wa.connect();
  }

  /**
   * 处理来自 Python 的命令
   * 
   * @param cmd - 发送命令
   */
  private async handleCommand(cmd: SendCommand): Promise<void> {
    if (cmd.type === 'send' && this.wa) {
      await this.wa.sendMessage(cmd.to, cmd.text);
    }
  }

  /**
   * 广播消息给所有连接的 Python 客户端
   * 
   * @param msg - 要广播的消息
   */
  private broadcast(msg: BridgeMessage): void {
    const data = JSON.stringify(msg);
    for (const client of this.clients) {
      if (client.readyState === WebSocket.OPEN) {
        client.send(data);
      }
    }
  }

  /**
   * 停止桥接服务器
   * 
   * 清理流程：
   * 1. 关闭所有客户端连接
   * 2. 关闭 WebSocket 服务器
   * 3. 断开 WhatsApp 连接
   */
  async stop(): Promise<void> {
    // 关闭所有客户端连接
    for (const client of this.clients) {
      client.close();
    }
    this.clients.clear();

    // 关闭 WebSocket 服务器
    if (this.wss) {
      this.wss.close();
      this.wss = null;
    }

    // 断开 WhatsApp
    if (this.wa) {
      await this.wa.disconnect();
      this.wa = null;
    }
  }
}
