#include "Dio24.h"
#include <stdio.h>

////////////////////////////////////////////////////////////////////////////////////////
// socket functions
////////////////////////////////////////////////////////////////////////////////////////

// connects to given IP_address and port with timeout in ms
// returns socket if ok or INVALID_SOCKET on error
// note: if IP_address = NULL connects to INADDR_ANY = "localhost"
SOCKET _connect(const char* IP_address, const char* port, int timeout) {
	int err = 0;
	SOCKET c = INVALID_SOCKET;
	struct addrinfo* result = NULL, * ptr = NULL;
	struct addrinfo ai;
	// init address information structure
	ZEROMEMORY(&ai, sizeof(ai));
	ai.ai_family = AF_INET;						// use IPv4 or IPv6 adress family
	ai.ai_socktype = SOCK_STREAM;				// streaming socket
	ai.ai_protocol = IPPROTO_TCP;				// TCP protocol

	// Resolve the server address and port
	if (getaddrinfo(IP_address, port, &ai, &result) == 0)
	{
		// attempt to connect to the first address returned by the call to getaddrinfo
		ptr = result;

		// Create a SOCKET for connecting to server
		c = socket(ptr->ai_family, ptr->ai_socktype, ptr->ai_protocol);
		if (c != INVALID_SOCKET)
		{
			// set socket to non-blocking
			unsigned long arg = 1;
			if (::ioctlsocket(c, FIONBIO, &arg) == SOCKET_ERROR) err = 1; // error setting non-blocking
			else {
				// connect to server
				if (::connect(c, ptr->ai_addr, (int)ptr->ai_addrlen) == SOCKET_ERROR) {
					// connection failed
					if ((WSAGetLastError() == WSAEWOULDBLOCK) && (timeout > 0)) {
						// connect with timeout
						fd_set set_w;
						FD_ZERO(&set_w);
						FD_SET(c, &set_w);
						timeval tv;
						tv.tv_sec = timeout / 1000;
						tv.tv_usec = (timeout % 1000) * 1000;
						err = select(0, NULL, &set_w, NULL, &tv);
						if (err == 1) {
							if (FD_ISSET(c, &set_w)) err = 0; // connection established within timeout
							else err = 2; // no connection?
						}
						else err = 3; // select failed or timeout
					}
					else err = 4; // other error connection or timeout = 0
				}
				else err = 0; // connection established immediately

				// set socket back to blocking
				arg = 0;
				if (::ioctlsocket(c, FIONBIO, &arg) == SOCKET_ERROR) err = err ? err : 3; // error setting non-blocking
			}

			if (err) {
				// error connecting to server
				CLOSESOCKET(c);
				c = INVALID_SOCKET;
			}
		}
		// free adress info structure returned by getaddrinfo
		freeaddrinfo(result);
	}
	return c;
}

// receive max. bytes into buffer within given timeout in ms
// returns number of received bytes, 0 on timeout and <0 on error
int _recv(SOCKET s, char* buffer, int bytes, int timeout) {
	int num = 0;
	unsigned long arg = 1;
	if (timeout == INFINITE) { // receive without timeout
		num = ::recv(s, buffer, bytes, 0);
	}
	else {
		// set socket to non-blocking
		if (::ioctlsocket(s, FIONBIO, &arg) == SOCKET_ERROR) num = -1; // error setting non-blocking
		else {
			// try receiving bytes
			// returns number of bytes, 0 if connection was closed or SOCKET_ERROR on error
			num = ::recv(s, buffer, bytes, 0);
			if (num == SOCKET_ERROR) {
				// receive failed
				if (WSAGetLastError() == WSAEWOULDBLOCK) {
					if (timeout == 0) num = 0; // no timeout selected: return 0
					else {	// receive with timeout
						fd_set set_r;
						FD_ZERO(&set_r);
						FD_SET(s, &set_r);
						timeval tv;
						tv.tv_sec = timeout / 1000;
						tv.tv_usec = (timeout % 1000) * 1000;
						// returns number of raised descriptors (expect 1), 0 on timeout
						num = select(0, &set_r, NULL, NULL, &tv);
						if (num == 1) {
							if (FD_ISSET(s, &set_r)) { // data available
								num = ::recv(s, buffer, bytes, 0);
							}
							else num = -3; // unexpected?
						}
						else if (num != 0) num = -3; // select failed
					}
				}
				else num = -2; // other error
			}
			// set socket back to blocking
			arg = 0;
			if (::ioctlsocket(s, FIONBIO, &arg) == SOCKET_ERROR) { num = num ? num : -4; } // error setting non-blocking
		}
	}
	return num;
}

////////////////////////////////////////////////////////////////////////////////////////
// lock locking function (used only during debugging)
////////////////////////////////////////////////////////////////////////////////////////

#ifdef _DEBUG

// for debugging we track number of locks/unlocks of lock. lock_count is protected by lock as well.
int lock_count = 0;

// try to acquire lock for LOCK_TIMEOUT ms.
// returns 1 on error, otherwise 0
int LOCK_OPEN(HANDLE lock) {
	if (lock == NULL) return 1;
	if (WaitForSingleObject(lock, LOCK_TIMEOUT) == WAIT_OBJECT_0) {
		++lock_count;
#ifdef SHOW_LOCK_INFO
		printf("%u: lock aquired %i (wait)\n", GetCurrentThreadId(), lock_count);
#endif
		return 0;
	}
	return 1;
}

// acquire lock with 0 ms timeout.
// returns 1 on error, otherwise 0
int LOCK_ERROR(HANDLE lock) {
	if (lock == NULL) return 1;
	if (WaitForSingleObject(lock, 0) == WAIT_OBJECT_0) {
		++lock_count;
#ifdef SHOW_LOCK_INFO
		printf("%u: lock aquired %i (no wait)\n", GetCurrentThreadId(), lock_count);
#endif
		return 0;
	}
	return 1;
}

// acquire lock, wait infinite until obtained. call from board_thread. cannot fail, but might wait forever.
void LOCK_OPEN_WAIT(HANDLE lock) {
	WaitForSingleObject(lock, INFINITE);
	++lock_count;
#ifdef SHOW_LOCK_INFO
	printf("%u: lock aquired %i (wait inf)\n", GetCurrentThreadId(), lock_count);
#endif
}

// call for every time LOCK_OPEN or LOCK_ERROR is called
// return value is 0 on error, nonzero on success.
int LOCK_RELEASE(HANDLE lock) {
	int ret = ReleaseMutex(lock);
	if (ret != 0) --lock_count;
#ifdef SHOW_LOCK_INFO
	if (ret != 0) printf("%u: lock released %i (ok)\n", GetCurrentThreadId(), lock_count);
	else          printf("%u: lock released %i (error)\n", GetCurrentThreadId(), lock_count);
#endif
	return ret;
}

#endif // _DEBUG

////////////////////////////////////////////////////////////////////////////////////////
// thread helper functions
////////////////////////////////////////////////////////////////////////////////////////

// connect to board and reset board
// returns STATUS_ACK on success and connected socket
// on error returns STATUS_IGNORE/STATUS_ABORT if user selected to ignore/abort, otherwise error code.
board_status thread_connect(SOCKET& sock, char* IP_port, int port_offset, int id) {
	board_status status = STATUS_NACK;
	// temporarily separate IP from port (needed by _connect)
	IP_port[port_offset - 1] = '\0';
	while (true) { // connect until success or ignore/abort
		sock = _connect(IP_port, IP_port + port_offset, CONNECT_TIMEOUT);
		if (sock != INVALID_SOCKET) break; // connected ok
		else { // notify user and ask if should Abort/Retry/Ignore
			int n;
			size_t num;

			const char* fmt = (id == 0) ? ERROR_CONNECTION_PRIM : ERROR_CONNECTION_SEC;
			num = (size_t) _scprintf(fmt, id, IP_port, IP_port + port_offset);
			if (num > 0) {
				char* message = new char[num + 1];
				if (message) {
					n = sprintf_s(message, num + 1, fmt, id, IP_port, IP_port + port_offset);
					if (n == num) {
						int err = MessageBoxA(NULL, message, DLL_INFO, MB_ICONEXCLAMATION | MB_ABORTRETRYIGNORE);
						if (err == IDABORT) { status = STATUS_ABORT; break; }// abort
						else if (err == IDRETRY) status = STATUS_NONE; // retry
						else if (err == IDIGNORE) { status = STATUS_IGNORE; break; } // ignore
					}
					delete[] message;
				}
			}
		}
	} // next retry if needed

	// revert IP_port separator
	IP_port[port_offset - 1] = sep[0];

	if (sock != INVALID_SOCKET) { // connected
#ifdef _DEBUG
		printf("connection %s ok\n", IP_port);
		//OutputDebugStringA("connect: ok\n");
#endif											
		// send open command
		SERVER_CMD cmd = SERVER_CMD_OPEN_RESOURCE;
		int num = send(sock, (char*)&cmd, sizeof(SERVER_CMD), 0);
		if (num != sizeof(SERVER_CMD)) status = STATUS_ESEND;
		else {
#ifdef _DEBUG									
			printf("open device: wait for ACK\n");
			//OutputDebugStringA("open device: wait for ACK\n");
#endif
			// wait for ACK
			cmd = 0;
			num = _recv(sock, (char*)&cmd, sizeof(SERVER_CMD), RECV_TIMEOUT);
			if (num != sizeof(SERVER_CMD)) {
				status = STATUS_ERECV;
#ifdef _DEBUG
#ifdef WIN32
				printf("open device: received %d instead of %u bytes\n", num, sizeof(SERVER_CMD));
#else
				printf("open device: received %d instead of %llu bytes\n", num, sizeof(SERVER_CMD));
#endif
				//OutputDebugStringA("open device: ACK\n");
#endif
			}
			else if (cmd != SERVER_ACK) {
				status = STATUS_EACK;
#ifdef _DEBUG
				printf("open device: NACK\n");
				//OutputDebugStringA("open device: ACK\n");
#endif
			}
			else {
#ifdef _DEBUG
				printf("open device: ACK\n");
				//OutputDebugStringA("open device: ACK\n");
#endif
				// reset device
				status = thread_reset(sock);
			}
		}
	}

	// on error close socket and delete IP_port
	if ((status != STATUS_ACK) && (sock != INVALID_SOCKET)) {
		closesocket(sock);
		sock = INVALID_SOCKET;
	}

	return status;
}

// close connection
// returns STATUS_ACK on success. sock is always closed.
board_status thread_close(SOCKET& sock) {
	board_status status = STATUS_NACK;

	// send close command
	SERVER_CMD cmd = SERVER_CMD_CLOSE;
	int num = send(sock, (char*)&cmd, sizeof(SERVER_CMD), 0);
	if (num != sizeof(SERVER_CMD)) status = STATUS_ESEND;
	else {
#ifdef _DEBUG
		printf("CLOSE: wait for ACK\n");
#endif
		// wait for ACK
		cmd = 0;
		num = _recv(sock, (char*)&cmd, sizeof(SERVER_CMD), RECV_TIMEOUT);
		if (num != sizeof(SERVER_CMD)) status = STATUS_ERECV;
		else if (cmd != SERVER_ACK) status = STATUS_EACK;
		else {
#ifdef _DEBUG
			printf("CLOSE: ACK\n");
#endif
			status = STATUS_ACK;
		}
	}

	// in all cases close socket 
	CLOSESOCKET(sock);
	sock = INVALID_SOCKET;

	return status;
}

// reset board
board_status thread_reset(SOCKET sock) {
	board_status status = STATUS_NACK;

	// send reset command
	SERVER_CMD cmd = SERVER_RESET;
	int num = send(sock, (char*)&cmd, sizeof(SERVER_CMD), 0);
	if (num != sizeof(SERVER_CMD)) status = STATUS_ESEND;
	else {
#ifdef _DEBUG
		printf("reset device: wait for ACK\n");
		//OutputDebugStringA("reset device: wait for ACK\n");
#endif
		// wait for ACK
		cmd = 0;
		num = _recv(sock, (char*)&cmd, sizeof(SERVER_CMD), RECV_TIMEOUT);
		if (num != sizeof(SERVER_CMD)) status = STATUS_ERECV;
		else if (cmd != SERVER_ACK) status = STATUS_EACK;
		else {
#ifdef _DEBUG
			printf("reset device: ACK\n");
			//OutputDebugStringA("reset device: ACK\n");
#endif
			status = STATUS_ACK;
		}
	}
	return status;
}

// configure board
// returns STATUS_ACK on success and config with actual configuration
board_status thread_config(SOCKET sock, struct client_config* config) {
	board_status status = STATUS_NACK;
	int num;
	uint32_t cf_old = config->config;
#if ( DIO_BYTES_PER_SAMPLE == 8 )
	// we send all allowed user bits without BPS96 bits (these 2 bits are handled by Out_Write)
	config->config &= (DIO_CTRL_USER & (~(DIO_CTRL_BPS96 | DIO_CTRL_BPS96_BRD)));
#else
	// we send all allowed user bits
	config->config &= DIO_CTRL_USER;
#endif
	uint32_t cf_exp = config->config;
	// send config and receive actual config
	num = send(sock, (char*)config, sizeof(struct client_config), 0);
	if (num != sizeof(struct client_config)) status = STATUS_ESEND;
	else {
		num = _recv(sock, (char*)config, sizeof(struct client_config), RECV_TIMEOUT);
		if (num != sizeof(struct client_config)) status = STATUS_ERECV;
		else {
#ifdef _DEBUG
			printf("set/get configuration 0x%08x\n", config->config);
#endif
			if ((config->config & DIO_CTRL_USER) != cf_exp) {
				status = STATUS_EBOARD; // unexpected return value?
#ifdef _DEBUG
				printf("get configuration 0x%08x not expected 0x%08x\n", config->config & DIO_CTRL_USER, cf_exp);
#endif
			}
			else {
#ifdef _DEBUG
				printf("set/get configuration 0x%08x ok\n", config->config);
#endif
				// save actual scan rate
				//*scanRate = (double)bd->conf->clock_Hz;
				status = STATUS_ACK;
			}
		}
	}
	config->config = cf_old;
	return status;
}

// get board status according to st->cmd
// if st->cmd = SERVER_GET_STATUS_IRQ or SERVER_GET_STATUS st is client_status
// if st->cmd = SERVER_GET_STATUS_FULL st is client_status_full
// returns STATUS_ACK on success and st filled with actual board status
board_status thread_status(SOCKET sock, struct client_status* st) {
	board_status status = STATUS_NACK;
	int num;
	SERVER_CMD rsp;
	if      (st->cmd == SERVER_GET_STATUS_IRQ)  rsp = SERVER_RSP_STATUS_IRQ;
	else if (st->cmd == SERVER_GET_STATUS)      rsp = SERVER_RSP_STATUS;
	else if (st->cmd == SERVER_GET_STATUS_FULL) rsp = SERVER_RSP_STATUS_FULL;
	else return STATUS_NACK;
	num = send(sock, (char*)&st->cmd, sizeof(SERVER_CMD), 0);
	if (num != sizeof(SERVER_CMD)) status = STATUS_ESEND;
	else {
		// wait for status. this might timeout and server returns NACK!
		// note: SERVER_GET_STATUS_IRQ can timeout and responds is SERVER_RSP_STATUS instead of SERVER_RSP_STATUS_IRQ
		num = _recv(sock, (char*)st, GET_DATA_BYTES(rsp), RECV_TIMEOUT);
		if (num != GET_DATA_BYTES(rsp)) status = STATUS_ERECV; // wrong number of bytes received
		else if (st->cmd == rsp) status = STATUS_ACK; // ok
		else if ((rsp == SERVER_RSP_STATUS_IRQ) && (st->cmd == SERVER_RSP_STATUS)) status = STATUS_ACK; // timeout but ok
		else status = STATUS_EACK; // wrong command received (usually NACK)
	}
	return status;
}

// send data to board
// returns STATUS_ACK on success
board_status thread_write(SOCKET sock, struct wr_data* data) {
	board_status status = STATUS_NACK;
	int num;
	struct client_data32* cd32 = new struct client_data32;
	if (cd32 == NULL) status = STATUS_NACK;
	else {
		// send command + buffer size
		cd32->cmd = SERVER_CMD_OUT_WRITE;
		cd32->data = data->samples * DIO_BYTES_PER_SAMPLE; // bytes to be sent (but buffer might be larger)
		num = send(sock, (char*)cd32, sizeof(struct client_data32), 0);
		if (num != sizeof(struct client_data32)) status = STATUS_ESEND;
		else {
#ifdef _DEBUG
			printf("prepare send %d samples: wait for ACK\n", data->samples);
#endif
			// wait for ACK
			cd32->cmd = 0;
			num = _recv(sock, (char*)&cd32->cmd, sizeof(SERVER_CMD), RECV_TIMEOUT);
			if (num != sizeof(SERVER_CMD)) status = STATUS_ERECV;
			else if (cd32->cmd != SERVER_ACK) status = STATUS_EACK;
			else {
#ifdef _DEBUG
				printf("prepare send %d samples: ACK\n", data->samples);
#endif
				// send data
				// TODO: this is blocking and not all data might be sent immediately
				//       in this case should wait until ready and send next data
#if ( DIO_BYTES_PER_SAMPLE == 8 )
				if (data->flags == WR_DATA_FLAG_ALL) {
#endif
					// send all data
					num = send(sock, (char*)data->buffer, data->samples * DIO_BYTES_PER_SAMPLE, 0);
					if (num != (data->samples * DIO_BYTES_PER_SAMPLE)) {
						status = STATUS_ESEND;
					}
#if ( DIO_BYTES_PER_SAMPLE == 8 )
				}
				else {
					uint32_t* buffer = new uint32_t[WR_DATA_BUFFER_SMPL*2]; // allocate buffer for time + data
					if (buffer) {
						int i, samples = data->samples;
						uint32_t *dst, *src = (uint32_t*)data->buffer;
						while (samples >= WR_DATA_BUFFER_SMPL) {
							dst = buffer; 
							if (data->flags == WR_DATA_FLAG_BRD_0) {
								// send first 8 bytes and skip last 4 bytes per sample
								for (i = 0; i < WR_DATA_BUFFER_SMPL; ++i) {
									*dst++ = *src++;
									*dst++ = *src++;
									++src;
								}
							}
							else {
								// send first 4 bytes, skip next 4 bytes and send last 4 bytes per sample
								for (i = 0; i < WR_DATA_BUFFER_SMPL; ++i) {
									*dst++ = *src++;
									++src;
									*dst++ = *src++;
								}
							}
							num = send(sock, (char*)buffer, WR_DATA_BUFFER_SMPL * DIO_BYTES_PER_SAMPLE, 0);
							if (num != (WR_DATA_BUFFER_SMPL * DIO_BYTES_PER_SAMPLE)) {
								status = STATUS_ESEND;
								break;
							};
							samples -= WR_DATA_BUFFER_SMPL;
						}
						if ((samples > 0) && (status != STATUS_ESEND)) {
							dst = buffer;
							if (data->flags == WR_DATA_FLAG_BRD_0) {
								// send first 8 bytes and skip last 4 bytes per sample
								for (i = 0; i < samples; ++i) {
									*dst++ = *src++;
									*dst++ = *src++;
									++src;
								}
							}
							else {
								// send first 4 bytes, skip next 4 bytes and send last 4 bytes per sample
								for (i = 0; i < samples; ++i) {
									*dst++ = *src++;
									++src;
									*dst++ = *src++;
								}
							}
							num = send(sock, (char*)buffer, samples * DIO_BYTES_PER_SAMPLE, 0);
							if (num != (samples * DIO_BYTES_PER_SAMPLE)) {
								status = STATUS_ESEND;
							}
						}
						delete [] buffer;
					}
				}
#endif
				if (status != STATUS_ESEND) {
					// all data sent: wait for ACK
#ifdef _DEBUG
					printf("send %d samples!\n", data->samples);
#endif
					// TODO: if we send a lot of data timeout for receive might be too short!
					//       for 120MiB on Cora-Z7-07s uploading takes 50s!
					cd32->cmd = 0;
					num = _recv(sock, (char*)&cd32->cmd, sizeof(SERVER_CMD), RECV_TIMEOUT_DATA);
					//num = ::recv(sock, (char*)&cd32->cmd, sizeof(SERVER_CMD), 0); // no timeout
					if (num == 0) status = STATUS_TIMEOUT_2;
					else if (num != sizeof(SERVER_CMD)) status = STATUS_ERECV;
					else if (cd32->cmd != SERVER_ACK) status = STATUS_EACK;
					else {
#ifdef _DEBUG
						printf("send %d samples: ACK\n", data->samples);
#endif
						status = STATUS_ACK;
					}
				}
			}
		}
		delete cd32;
	}
	return status;
}

// start board with given repetitions
// returns STATUS_ACK on success
board_status thread_start(SOCKET sock, int reps) {
	board_status status = STATUS_NACK;
	int num;
	struct client_data32* cd32 = new struct client_data32;
	if (cd32 == NULL) status = STATUS_EMEM;
	else {
		cd32->cmd = SERVER_CMD_OUT_START;
		cd32->data = reps;
		num = send(sock, (char*)cd32, sizeof(struct client_data32), 0);
		if (num != sizeof(struct client_data32)) status = STATUS_ESEND;
		else {
#ifdef _DEBUG
			printf("OUT_START: wait for ACK\n");
#endif
			// wait for ACK
			cd32->cmd = 0;
			num = _recv(sock, (char*)cd32, sizeof(SERVER_CMD), RECV_TIMEOUT);
			if (num == 0) status = STATUS_TIMEOUT_2;
			else if (num != sizeof(SERVER_CMD)) status = STATUS_ERECV;
			else if (cd32->cmd != SERVER_ACK) status = STATUS_EACK;
			else {
#ifdef _DEBUG
				printf("OUT_START: ACK\n");
#endif
				status = STATUS_ACK;
			}
		}
	}
	return status;
}

// stop board
// returns STATUS_ACK on success
board_status thread_stop(SOCKET sock) {
	board_status status = STATUS_NACK;
	int num;
	// send stop command
	SERVER_CMD cmd = SERVER_CMD_OUT_STOP;
	num = send(sock, (char*)&cmd, sizeof(SERVER_CMD), 0);
	if (num != sizeof(SERVER_CMD)) status = STATUS_ESEND;
	else {
#ifdef _DEBUG
		printf("OUT_STOP: wait for ACK\n");
#endif
		// wait for ACK
		cmd = 0;
		num = _recv(sock, (char*)&cmd, sizeof(SERVER_CMD), RECV_TIMEOUT);
		if (num != sizeof(SERVER_CMD)) status = STATUS_ERECV;
		else if (cmd != SERVER_ACK) status = STATUS_EACK;
		else {
#ifdef _DEBUG
			printf("OUT_STOP: ACK\n");
#endif
			status = STATUS_ACK;
		}
	}
	return status;
}

// send test command to server
board_status thread_test(SOCKET sock, void *data) {
	board_status status = STATUS_NACK;

	// send test command
	struct client_data32* cd32 = new struct client_data32;
	if (cd32 == NULL) status = STATUS_EMEM;
	else {
		cd32->cmd = SERVER_TEST;
		cd32->data = 0; // (uint32_t)data;
		int num = send(sock, (char*)cd32, sizeof(client_data32), 0);
		if (num != sizeof(client_data32)) status = STATUS_ESEND;
		else {
#ifdef _DEBUG
			printf("test: wait for ACK\n");
			//OutputDebugStringA("test: wait for ACK");
#endif
			// wait for ACK
			cd32->cmd = 0;
			cd32->data = 0;
			num = _recv(sock, (char*)cd32, sizeof(client_data32), RECV_TIMEOUT);
			if (num != sizeof(SERVER_CMD)) status = STATUS_ERECV;
			else if (cd32->cmd != SERVER_ACK) status = STATUS_EACK;
			else {
#ifdef _DEBUG
				printf("test: ACK\n");
				//OutputDebugStringA("test: ACK");
#endif
				status = STATUS_ACK;
			}
		}
		delete cd32;
	}
	return status;
}

////////////////////////////////////////////////////////////////////////////////////////
// board threads
////////////////////////////////////////////////////////////////////////////////////////

DWORD WINAPI board_thread(LPVOID lpParam) {
	struct board_info* bd = (struct board_info*)lpParam;
	thread_cmd* cmd;
	SOCKET sock = INVALID_SOCKET;		// set/reset by SERVER_CMD_OPEN(_RESOURCE)/CLOSE
	thread_cb callback = NULL;			// set/reset by THREAD_CMD_CB
	void* user_data = NULL;				// set/reset by THREAD_CMD_CB
	struct client_config* config = NULL; // set/reset by SERVER_CMD_OUT_CONFIG/CLOSE
	thread_cmd* cmd_status = NULL;		// set/reset by SERVER_CMD_OUT_START/STOP
	unsigned timeout = INFINITE;		// timeout for close command

#ifdef _DEBUG
	int id = bd->id;					// save board ID for debugging messages
	printf("board_thread %d (%u) start\n", id, GetCurrentThreadId());
#endif

	// create send and receive queue
	bd->send_queue = new thread_queue;
	bd->recv_queue = new thread_queue;

	// insert startup status: 1 on success, 0 on error
	bd->recv_queue->add(new thread_cmd(THREAD_START, (void*)1), PRIORITY_NORMAL);
	// signal startup finished and queues available (even on error)
	SetEvent(hStartup);

	while (true) {
		// wait/check for command(s) in queue
		// if board is running we use 0 timeout and we check only if queue is empty
		cmd = bd->send_queue->remove(bd->running ? 0 : timeout);
		if ((cmd == NULL) && (!bd->running) && (timeout != INFINITE)) {
			// timeout: exit thread now if board was not reconnected
			cmd = new thread_cmd(THREAD_EXIT, (void*)NULL);
		}
		timeout = INFINITE;			// reset timeout in all cases
		if (cmd) {
			// command received
			cmd->status = STATUS_NACK;	// indicate no success in case of failure
			switch (cmd->cmd) {
			case SERVER_CMD_OPEN:
			case SERVER_CMD_OPEN_RESOURCE:
				// connect to board and reset board
				// data = NULL (bd->IP_port and bd->port must be valid and cannot change afterwards)
				// returns STATUS_ACK on success and socket is connected
				// on error returns STATUS_IGNORE if user selected to ignore, otherwise error code.
				if ((bd->IP_port != NULL) && (bd->port_offset > 0) && (cmd->data.ptr == NULL)) {
					if (sock == INVALID_SOCKET) {
						cmd->status = thread_connect(sock, bd->IP_port, bd->port_offset, bd->id);
#ifdef _DEBUG
						printf("board_thread %d (%hu) connect %s (%i)\n", id, bd->thread_id, bd->IP_port, cmd->status);
#endif
					}
					else { // board already connected (close called but open command within timeout)
						cmd->status = thread_reset(sock);
						if (cmd->status == STATUS_ACK) cmd->status = STATUS_ACTIVE;
#ifdef _DEBUG
						printf("board_thread %d (%hu) re-connect (reset) %s (%i)\n", id, bd->thread_id, bd->IP_port, cmd->status);
#endif
					}
				}
				break;
			case SERVER_CMD_CLOSE:
				// close connection
				// data = timeout in ms or 0
				// returns STATUS_ACK on success. sock is always closed.
				if (sock != INVALID_SOCKET) {
					// stop board if running
					if (bd->running) {
						thread_stop(sock);
						bd->running = false;
					}
				}
				// close connection if timeout == 0, otherwise program timeout
				if (cmd->data.u32 == 0) {
					cmd->status = thread_close(sock);
					// delete configuration
					if (config) { delete config; config = NULL; }
#ifdef _DEBUG
					printf("board_thread %d (%hu) close %s now (%i)\n", id, bd->thread_id, bd->IP_port, cmd->status);
#endif
				}
				else {
					timeout = cmd->data.u32;
					cmd->status = STATUS_ACTIVE;
#ifdef _DEBUG
					printf("board_thread %d (%hu) close %s with timout %ims\n", id, bd->thread_id, bd->IP_port, timeout);
#endif
				}
				break;
			case SERVER_RESET:
				// reset board
				// data = NULL
				// returns STATUS_ACK on success.
				if ((sock != INVALID_SOCKET) && (cmd->data.ptr == NULL)) {
					// stop board if running
					if (bd->running) {
						thread_stop(sock);
						bd->running = false;
					}
					// reset board
					cmd->status = thread_reset(sock);
				}
				break;
			case SERVER_CMD_OUT_CONFIG:
				// configure board
				// data = struct client_config* (deleted by thread)
				// returns STATUS_ACK on success and config with actual configuration
				if ((sock != INVALID_SOCKET) /*&& (config == NULL)*/ && (cmd->data.ptr != NULL) && (!bd->running)) {
					if (config) delete config;
					config = (struct client_config*)cmd->data.ptr;
					cmd->status = thread_config(sock, config);
					if (cmd->status != STATUS_ACK) {
						delete config;
						config = NULL;
					}
					// do not return data
					cmd->data.ptr = NULL;
				}
				break;
			case SERVER_CMD_OUT_STATUS:
			case SERVER_GET_STATUS_FULL:
				// get status when board is not running (otherwise done automatically after SERVER_CMD_OUT_START)
				// data = NULL
				// returns STATUS_ACK on success and data = struct client_status/_full * with board status
				if ((sock != INVALID_SOCKET) && (cmd->data.ptr == NULL)) {
					if (cmd->cmd == SERVER_CMD_OUT_STATUS) cmd->data.ptr = new struct client_status;
					else cmd->data.ptr = new struct client_status_full;
					if (cmd->data.ptr) {
						// get board status
						// returns STATUS_ACK on success and status with actual board status
						struct client_status* st = (struct client_status*)cmd->data.ptr;
						st->cmd = (cmd->cmd == SERVER_CMD_OUT_STATUS) ? SERVER_GET_STATUS : SERVER_GET_STATUS_FULL;
						cmd->status = thread_status(sock, st);
					}
				}
				break;
			case SERVER_CMD_OUT_WRITE:
				// send data to board
				// data = struct wr_data* (deleted by thread but data->buffer not deleted)
				// returns STATUS_ACK on success
				// TODO: for streaming mode board can be running
				if ((sock != INVALID_SOCKET) && (cmd->data.ptr != NULL) && (!bd->running)) {
					cmd->status = thread_write(sock, (struct wr_data*)cmd->data.ptr);
					//delete cmd->data;
					//cmd->data = NULL;
				}
				break;
			case SERVER_CMD_OUT_START:
				// start board with configured repetitions
				// data = NULL
				// returns STATUS_ACK on success and continuously updates status information
				if ((sock != INVALID_SOCKET) && (config != NULL) && (!bd->running)) {
					cmd->status = thread_start(sock, config->reps);
					if (cmd->status == STATUS_ACK) {
						bd->running = true;
					}
				}
				break;
			case SERVER_CMD_OUT_STOP:
				// stop board and updating of status 
				// data = NULL
				// returns STATUS_ACK on success
				// get_status might have been reset automatically
				// note: bd->running might be automatically reset, so we do not check this here.
				if (sock != INVALID_SOCKET) {
					cmd->status = thread_stop(sock);
					bd->running = false;
					// reset board. 
					cmd->status = thread_reset(sock);
				}
				break;
			case THREAD_CMD_CB:
				// register callback 
				// data = struct cb_data* (deleted by thread) or NULL if unregister callback
				// returns STATUS_ACTIVE or STATUS_ACK on success
				if (cmd->data.ptr) { // register new callback (overwrites active one)
					callback = ((struct cb_data*)cmd->data.ptr)->callback;
					user_data = ((struct cb_data*)cmd->data.ptr)->user_data;
					if (callback != NULL) cmd->status = STATUS_ACTIVE;
					else cmd->status = STATUS_ACK; // same as unregister data
					delete cmd->data.ptr;
					cmd->data.ptr = NULL;
				}
				else { // unregister active callback
					callback = NULL;
					user_data = NULL;
					cmd->status = STATUS_ACK;
				}
				break;
			case THREAD_EXIT:
				// exit thread: terminate thread without adding response to recv_queue
				// if board has not been re-connected closes thread and deletes all resources of thread including queues.
				// if board has been re-connected does nothing.
				// for details see comments in DIO64_OpenResource (Dio24.cpp)
				// obtain lock and check if board has not been re-connected
				LOCK_OPEN_WAIT(lock);
				if (bd->board == BOARD_NONE) { // exit thread if board not re-opened
					if (sock != INVALID_SOCKET) {
						// stop board if running
						if (bd->running) {
							thread_stop(sock);
							bd->running = false;
						}
						// close connection
						cmd->status = thread_close(sock);
					}
					bd->thread_hdl = NULL;	// otherwise close_board would insert THREAD_EXIT command into queue and wait.
					bd->thread_id = 0;
					// delete send and receive queues (they are emptied in destructor)
					delete bd->send_queue;
					bd->send_queue = NULL;
					delete bd->recv_queue;
					bd->recv_queue = NULL;
					close_board(bd);			// removes board from boards list and deletes board
					bd = NULL;					// board is invalid: this will break loop
				}
				LOCK_RELEASE(lock);
#ifdef _DEBUG
				if (bd) {
					printf("board_thread %d (%hu) close %s aborted\n", id, bd->thread_id, bd->IP_port);
				}
				else {
					printf("board_thread %d (%u) closed\n", id, GetCurrentThreadId());
				}
#endif
				delete cmd;
				cmd = NULL;
				break;
			case SERVER_TEST:
				// send test command to server
				if (sock != INVALID_SOCKET) {
					cmd->status = thread_test(sock, cmd->data.ptr);
				}
			}
			if (cmd) { // return command into recv queue
				bd->recv_queue->add(cmd, PRIORITY_NORMAL);
			}
		}
		
		// if THREAD_EXIT and board not re-opened, break from loop
		if (bd == NULL) break;

		// during sequence running get status and callback if enabled
		if (bd->running) {
			int err = 0, num;
			struct client_status* status;
			// allocate cmd_status if needed or take old one received from update()
			if (cmd_status == NULL) {
				status = new struct client_status;
				if (status) {
					cmd_status = new thread_cmd(SERVER_CMD_OUT_STATUS, status);
				}
			}
			else status = (struct client_status*)cmd_status->data.ptr;
			if (cmd_status && status) {
				// get board status
				// returns STATUS_ACK on success and status with actual board status.
				// in case of timeout polls 1x with status->cmd = SERVER_GET_STATUS.
				status->cmd = SERVER_GET_STATUS_IRQ;
				cmd_status->status = thread_status(sock, status);

				// callback if no error
				// callback returns 0 if ok, otherwise stop calling callback
				if ((cmd_status->status == STATUS_ACK) && (callback != NULL)) {
					num = (*callback)(status->status.board_time, status->status.status, user_data);
					if (num != 0) { callback = NULL; user_data = NULL; }
				}

				// update status also on error
				// this exchanges last status if was last entry in queue, or creates a new entry
				// returns last status (which we re-use for next get_status)
				cmd_status = bd->recv_queue->update(cmd_status);
				/*{
					thread_cmd *last = NULL;
					int i = recv_queue[id]->debug(last);
					int num = _scprintf("thread %d, queue %d entries, last = 0x%x", id, i, last ? last->cmd : NULL);
					if (num > 0) {
						char *message = new char[num + 1];
						if (message) {
							int n = sprintf_s(message, num + 1, "thread %d, queue %d entries, last = 0x%x", id, i, last ? last->cmd : NULL);
							if (n == num) {
								MessageBoxA(NULL, message, "debug", MB_OK);
							}
							delete[] message;
						}
					}
				}*/
				// check if board is in end or not running state: stop getting status
				if ( (status->status.status & DIO_STATUS_END) || ((status->status.status & DIO_STATUS_RUN) == 0) ) {
					bd->running = false;
					// check if board has lost lock for short time and has reached end state: notify user with modeless dialog box
					if ((status->status.status & (DIO_STATUS_ERR_LOCK | DIO_STATUS_END)) == (DIO_STATUS_ERR_LOCK | DIO_STATUS_END)) {
						SendMessage(dlg_hWnd, WM_COMMAND, (WPARAM)ID_MB_SHOW, (LPARAM)bd->board);
					}
				}
			}
			// on error: do nothing except update status and retry next time
		}
	} // next loop

	// ensure socket is closed
	if (sock != INVALID_SOCKET) closesocket(sock);

	// delete configuration
	if (config) delete config;

	// delete last status
	if (cmd_status) {
		if (cmd_status->data.ptr) delete cmd_status->data.ptr;
		delete cmd_status;
	}

#ifdef _DEBUG
	printf("board_thread %d (%u) exit\n", id, GetCurrentThreadId());
#endif
	return 0;
}
