export default class WebSocketManager {
    private ws: WebSocket | null = null
    private url: string
    private reconnectTimer: NodeJS.Timeout | null = null
    private messageHandlers: Array<(data: any) => void> = []
    
    constructor(url: string) {
      this.url = url
      this.connect()
    }
    
    private connect() {
      try {
        console.log('Connecting to WebSocket:', this.url)
        this.ws = new WebSocket(this.url)
        
        this.ws.onopen = () => {
          console.log('WebSocket connected')
          // Clear any reconnect timer
          if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer)
            this.reconnectTimer = null
          }
        }
        
        this.ws.onclose = () => {
          console.log('WebSocket disconnected')
          // Try to reconnect after a delay
          this.reconnectTimer = setTimeout(() => this.connect(), 2000)
        }
        
        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error)
        }
        
        this.ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            console.log('Received WebSocket message:', data)
            this.messageHandlers.forEach(handler => handler(data))
          } catch (error) {
            console.error('Error parsing WebSocket message:', error)
          }
        }
      } catch (error) {
        console.error('Error connecting to WebSocket:', error)
        // Try to reconnect after a delay
        this.reconnectTimer = setTimeout(() => this.connect(), 2000)
      }
    }
    
    public send(data: any) {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        this.ws.send(JSON.stringify(data))
      } else {
        console.error('WebSocket not connected')
      }
    }
    
    public onMessage(handler: (data: any) => void) {
      this.messageHandlers.push(handler)
    }
    
    public disconnect() {
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer)
        this.reconnectTimer = null
      }
      
      if (this.ws) {
        this.ws.close()
        this.ws = null
      }
    }
  }