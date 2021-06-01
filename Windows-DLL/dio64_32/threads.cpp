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
// thread helper functions
////////////////////////////////////////////////////////////////////////////////////////

// connect to board and reset board
// returns STATUS_ACK on success and connected socket
// on error returns STATUS_IGNORE if user selected to ignore, otherwise error code.
// note on difference of slave_id and id:
//		data->slave_id = master (0) or slave board (>0)
//		id = thread id = total board id
board_status thread_connect(SOCKET& sock, char* IP_port, int port, int id, int slave_id) {
	board_status status = STATUS_NACK;
	// temporarily separate IP from port (needed by _connect)
	IP_port[port - 1] = '\0';
	while (true) { // connect until success or ignore/abort
		sock = _connect(IP_port, IP_port + port, CONNECT_TIMEOUT);
		if (sock != INVALID_SOCKET) break; // connected ok
		else { // notify user and ask if should Abort/Retry/Ignore
			int num, n;
			if (slave_id == SLAVE_ID_MASTER)
				num = _scprintf(ERROR_CONNECTION_MASTER, id, IP_port, IP_port + port);
			else
				num = _scprintf(ERROR_CONNECTION_SLAVE, id, slave_id, IP_port, IP_port + port);
			if (num > 0) {
				char* message = new char[num + 1];
				if (message) {
					if (slave_id == SLAVE_ID_MASTER)
						n = sprintf_s(message, num + 1, ERROR_CONNECTION_MASTER, id, IP_port, IP_port + port);
					else
						n = sprintf_s(message, num + 1, ERROR_CONNECTION_SLAVE, id, slave_id, IP_port, IP_port + port);
					if (n == num) {
						int err = MessageBoxA(NULL, message, DLL_INFO, MB_ICONEXCLAMATION | MB_ABORTRETRYIGNORE);
						if (err == IDABORT) { status = STATUS_NACK; break; }// abort
						else if (err == IDRETRY) status = STATUS_NONE; // retry
						else if (err == IDIGNORE) { status = STATUS_IGNORE; break; } // ignore
					}
					delete[] message;
				}
			}
		}
	} // next retry if needed

	// revert IP_port separator
	IP_port[port - 1] = sep[0];

	if (sock != INVALID_SOCKET) { // connected
#ifdef _DEBUG
		printf("connection %s:%s ok\n", IP_port, IP_port + port + 1);
		OutputDebugStringA("connecting: ok");
#endif											
		// send open command
		SERVER_CMD cmd = SERVER_CMD_OPEN_RESOURCE;
		int num = send(sock, (char*)&cmd, sizeof(SERVER_CMD), 0);
		if (num != sizeof(SERVER_CMD)) status = STATUS_ESEND;
		else {
#ifdef _DEBUG									
			printf("open device: wait for ACK\n");
			OutputDebugStringA("open device: wait for ACK");
#endif
			// wait for ACK
			cmd = 0;
			num = _recv(sock, (char*)&cmd, sizeof(SERVER_CMD), RECV_TIMEOUT);
			if (num != sizeof(SERVER_CMD)) status = STATUS_ERECV;
			else if (cmd != SERVER_ACK) status = STATUS_EACK;
			else {
#ifdef _DEBUG
				printf("open device: ACK\n");
				OutputDebugStringA("open device: ACK");
#endif
				// reset device
				status = thread_reset(sock);
			}
		}
	}

	// close socket and delete IP_port on error
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
		OutputDebugStringA("reset device: wait for ACK");
#endif
		// wait for ACK
		cmd = 0;
		num = _recv(sock, (char*)&cmd, sizeof(SERVER_CMD), RECV_TIMEOUT);
		if (num != sizeof(SERVER_CMD)) status = STATUS_ERECV;
		else if (cmd != SERVER_ACK) status = STATUS_EACK;
		else {
#ifdef _DEBUG
			printf("reset device: ACK\n");
			OutputDebugStringA("reset device: ACK");
#endif
			status = STATUS_ACK;
		}
	}
	return status;
}

// configure board
// returns STATUS_ACK on success and config with actual configuration
board_status thread_config(SOCKET sock, struct client_config* config, bool is_master) {
	board_status status = STATUS_NACK;
	int num;
	uint32_t cf = config->config & DIO_CTRL_USER;
	if (cf == config->config) { // check allowed bits
		// for slave we set trigger and external clock bits and board 1 if BPS96
		if (is_master) {
			//config->config |= DIO_CTRL_TRG_START_EN;
		}
		else {
			if (config->config & DIO_CTRL_BPS96)
				config->config |= DIO_CTRL_EXT_CLK | DIO_CTRL_TRG_START_EN | DIO_CTRL_BPS96_BRD;
			else
				config->config |= DIO_CTRL_EXT_CLK | DIO_CTRL_TRG_START_EN;
		}
		cf = config->config;
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
				if ((config->config & DIO_CTRL_USER) != cf) {
					status = STATUS_EBOARD; // unexpected return value?
#ifdef _DEBUG
					printf("get configuration 0x%08x not 0x%08x\n", config->config, cf);
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
	}
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
	if (st->cmd == SERVER_GET_STATUS_IRQ) rsp = SERVER_RSP_STATUS;
	else if (st->cmd == SERVER_GET_STATUS) rsp = SERVER_RSP_STATUS;
	else if (st->cmd == SERVER_GET_STATUS_FULL) rsp = SERVER_RSP_STATUS_FULL;
	else return STATUS_NACK;
	num = send(sock, (char*)&st->cmd, sizeof(SERVER_CMD), 0);
	if (num != sizeof(SERVER_CMD)) status = STATUS_ESEND;
	else {
		// wait for status (might timeout)
		num = _recv(sock, (char*)st, GET_DATA_BYTES(rsp), RECV_TIMEOUT);
		if (num != GET_DATA_BYTES(rsp)) status = STATUS_ERECV; // timeout
		else if (st->cmd != rsp) status = STATUS_EACK;
		else status = STATUS_ACK; // success
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
		cd32->data = data->bytes; // bytes to be sent
		num = send(sock, (char*)cd32, sizeof(struct client_data32), 0);
		if (num != sizeof(struct client_data32)) status = STATUS_ESEND;
		else {
#ifdef _DEBUG
			printf("prepare send %d bytes: wait for ACK\n", data->bytes);
#endif
			// wait for ACK
			cd32->cmd = 0;
			num = _recv(sock, (char*)&cd32->cmd, sizeof(SERVER_CMD), RECV_TIMEOUT);
			if (num != sizeof(SERVER_CMD)) status = STATUS_ERECV;
			else if (cd32->cmd != SERVER_ACK) status = STATUS_EACK;
			else {
#ifdef _DEBUG
				printf("prepare send %d bytes: ACK\n", data->bytes);
#endif
				// send data
				// todo: this is blocking and not all data might be sent immediately
				//       in this case should wait until ready and send next data
				num = send(sock, (char*)data->buffer, data->bytes, 0);
				if (num != data->bytes) status = STATUS_ESEND;
				else {
					// all data sent: wait for ACK
#ifdef _DEBUG
					printf("send %d bytes!\n", data->bytes);
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
						printf("send %d bytes: ACK\n", data->bytes);
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
		cd32->data = (uint32_t)data;
		int num = send(sock, (char*)cd32, sizeof(client_data32), 0);
		if (num != sizeof(client_data32)) status = STATUS_ESEND;
		else {
#ifdef _DEBUG
			printf("test: wait for ACK\n");
			OutputDebugStringA("test: wait for ACK");
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
				OutputDebugStringA("test: ACK");
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
	int run = 1;
	struct board_info* bd = (struct board_info*)lpParam;
	thread_cmd* cmd;
	SOCKET sock = INVALID_SOCKET;		// set/reset by SERVER_CMD_OPEN(_RESOURCE)/CLOSE
	thread_cb callback = NULL;			// set/reset by THREAD_CMD_CB
	void* user_data = NULL;				// set/reset by THREAD_CMD_CB
	struct client_config* config = NULL; // set/reset by SERVER_CMD_OUT_CONFIG/CLOSE
	thread_cmd* cmd_status = NULL;		// set/reset by SERVER_CMD_OUT_START/STOP
	unsigned timeout = INFINITE;		// timeout for close command

#ifdef _DEBUG
	printf("board_thread pid %hu, board id %d start\n", GetCurrentThreadId(), bd->id);
#endif

	// create send and receive queue
	bd->send_queue = new thread_queue;
	bd->recv_queue = new thread_queue;

	// insert startup status: 1 on success, 0 on error
	bd->recv_queue->add(new thread_cmd(THREAD_START, (void*)1), PRIORITY_NORMAL);
	// signal startup finished and queues available (even on error)
	SetEvent(hStartup);

	while (run) {
		// wait/check for command(s) in queue
		// if board is running we use 0 timeout and we check only if queue is empty
		cmd = bd->send_queue->remove(bd->running ? 0 : timeout);
		if ((cmd == NULL) && (!bd->running) && (timeout != INFINITE)) {
			// timeout: close connection now
			cmd = new thread_cmd(SERVER_CMD_CLOSE, NULL);
		}
		if (cmd) {
			// command received
			timeout = INFINITE;			// reset timeout
			cmd->status = STATUS_NACK;	// indicate no success in case of failure
			switch (cmd->cmd) {
			case SERVER_CMD_OPEN:
			case SERVER_CMD_OPEN_RESOURCE:
				// connect to board and reset board
				// data = NULL (bd->IP_port and bd->port must be valid and cannot change afterwards)
				// returns STATUS_ACK on success and socket is connected
				// on error returns STATUS_IGNORE if user selected to ignore, otherwise error code.
				if ((bd->IP_port != NULL) && (bd->port > 0) && (cmd->data == NULL)) {
					if (sock == INVALID_SOCKET) {
						cmd->status = thread_connect(sock, bd->IP_port, bd->port, bd->id, bd->slave_id);
					}
					else { // board already connected (close called but open command within timeout)
						cmd->status = thread_reset(sock);
						if (cmd->status == STATUS_ACK) cmd->status = STATUS_ACTIVE;
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
					// close connection if timeout == 0, otherwise program timeout
					if (((unsigned)cmd->data) == 0) {
						cmd->status = thread_close(sock);
						// delete configuration
						if (config) { delete config; config = NULL; }
					}
					else {
						timeout = (unsigned)cmd->data;
						cmd->status = STATUS_ACTIVE;
					}
				}
				break;
			case SERVER_RESET:
				// reset board
				// data = NULL
				// returns STATUS_ACK on success.
				if ((sock != INVALID_SOCKET) && (cmd->data == NULL)) {
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
				if ((sock != INVALID_SOCKET) /*&& (config == NULL)*/ && (cmd->data != NULL) && (!bd->running)) {
					if (config) delete config;
					config = (struct client_config*)cmd->data;
					cmd->status = thread_config(sock, config, bd->slave_id == SLAVE_ID_MASTER);
					if (cmd->status != STATUS_ACK) {
						delete config;
						config = NULL;
					}
					// do not return data
					cmd->data = NULL;
				}
				break;
			case SERVER_CMD_OUT_STATUS:
			case SERVER_GET_STATUS_FULL:
				// get status when board is not running (otherwise done automatically after SERVER_CMD_OUT_START)
				// data = NULL
				// returns STATUS_ACK on success and data = struct client_status/_full * with board status
				if ((sock != INVALID_SOCKET) && (cmd->data == NULL)) {
					if (cmd->cmd == SERVER_CMD_OUT_STATUS) cmd->data = new struct client_status;
					else cmd->data = new struct client_status_full;
					if (cmd->data) {
						// get board status
						// returns STATUS_ACK on success and status with actual board status
						struct client_status* st = (struct client_status*)cmd->data;
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
				if ((sock != INVALID_SOCKET) && (cmd->data != NULL) && (!bd->running)) {
					cmd->status = thread_write(sock, (struct wr_data*)cmd->data);
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
				}
				break;
			case THREAD_CMD_CB:
				// register callback 
				// data = struct cb_data* (deleted by thread) or NULL if unregister callback
				// returns STATUS_ACTIVE or STATUS_ACK on success
				if (bd->slave_id == SLAVE_ID_MASTER) {
					if (cmd->data) { // register new callback (overwrites active one)
						callback = ((struct cb_data*)cmd->data)->callback;
						user_data = ((struct cb_data*)cmd->data)->user_data;
						if (callback != NULL) cmd->status = STATUS_ACTIVE;
						else cmd->status = STATUS_ACK; // same as unregister data
						delete cmd->data;
						cmd->data = NULL;
					}
					else { // unregister active callback
						callback = NULL;
						user_data = NULL;
						cmd->status = STATUS_ACK;
					}
				}
				break;
			case THREAD_EXIT:
				// exit thread: terminate thread without adding response to recv_queue
				// this closes thread and deletes all resources of thread including queues.
				if (sock != INVALID_SOCKET) {
					// stop board if running
					if (bd->running) {
						thread_stop(sock);
						bd->running = false;
					}
					// close connection
					cmd->status = thread_close(sock);
				}
				delete cmd;
				cmd = NULL;
				run = 0;
				break;
			case SERVER_TEST:
				// send test command to server
				if (sock != INVALID_SOCKET) {
					cmd->status = thread_test(sock, cmd->data);
				}
			}
			if (cmd) { // return command into recv queue
				bd->recv_queue->add(cmd, PRIORITY_NORMAL);
			}
		}
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
			else status = (struct client_status*)cmd_status->data;
			if (cmd_status && status) {
				// get board status
				// returns STATUS_ACK on success and status with actual board status
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
				// if in end or error state stop getting status
				if (status->status.status & (DIO_STATUS_ERROR | DIO_STATUS_END)) {
					bd->running = false;
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
		if (cmd_status->data) delete cmd_status->data;
		delete cmd_status;
	}

	// delete send and receive queues (they are emptied in destructor)
	// note: this is done only with THREAD_EXIT command and main thread is supposed to not use queues anymore!
	delete bd->send_queue;
	bd->send_queue = NULL;
	delete bd->recv_queue;
	bd->recv_queue = NULL;

#ifdef _DEBUG
	printf("board_thread pid %hu, board id %d exit\n", GetCurrentThreadId(), bd->id);
#endif
	return 0;
}
