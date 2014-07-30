# Written to target Python 3.x exclusively.

import time
import errno
from .marquise_cffi import FFI, cprint, cstring, len_cstring, is_cnull, C_LIBMARQUISE
class Marquise(object):

	"""
	This libmarquise binding provides an interface to submit simple and
	extended datapoints, and provide "source dictionaries" containing
	metadata about datapoints.
	"""

	def __init__(self, namespace, debug=False):
		"""Establish a marquise context for the provided namespace,
		getting spool filenames.

		Arguments:
		namespace -- must be lowercase alphanumeric ([a-z0-9]+).
		debug -- if debug is True, debugging output will be printed.
		"""
		self.debug_enabled = debug
		self.namespace_c = cstring(namespace)
		self.marquise_ctx = C_LIBMARQUISE.marquise_init(self.namespace_c)
		if is_cnull(self.marquise_ctx):
			if FFI.errno == errno.EINVAL:
				raise ValueError("Invalid namespace: {}".format(namespace))
			raise RuntimeError("Something went wrong, got NULL instead of a marquise_ctx. build_spool_path() failed, or malloc failed. errno is {}".format(FFI.errno))

		self.spool_path_points   = cprint(self.marquise_ctx.spool_path_points)
		self.spool_path_contents = cprint(self.marquise_ctx.spool_path_contents)

	def __str__(self):
		"""Return a human-readable description of the current Marquise context."""
		return "<Marquise handle spooling to {} and {}>".format(self.spool_path_points, self.spool_path_contents)

	def __debug(self, msg):
		"""Print `msg` if debugging is enabled on this instance. Intended for internal use."""
		if self.debug_enabled:
			print("DEBUG: {}".format(msg))

	def close(self):
		"""Close the Marquise context, ensuring data is flushed and
		spool files are closed.

		This should always be closed explicitly, as there's no
		guarantees that it will happen when the instance is deleted.
		"""
		if self.marquise_ctx is None:
			self.__debug("Marquise handle is already closed, will do nothing.")
			# Multiple close() calls are okay.
			return

		self.__debug("Shutting down Marquise handle spooling to {} and {}".format(self.spool_path_points, self.spool_path_contents))

		# At the time of writing this always succeeds (returns 0).
		C_LIBMARQUISE.marquise_shutdown(self.marquise_ctx)

		# Signal that our context is no longer valid.
		self.marquise_ctx = None

	@staticmethod
	def hash_identifier(identifier):
		"""Return the siphash-2-4 of the `identifier`, using a static
		all-zeroes key.

		The output is an integer, which is used as the `address` of
		datapoints belonging to the given `identifier` string.
		"""
		return C_LIBMARQUISE.marquise_hash_identifier(cstring(identifier), len(identifier) )

	@staticmethod
	def current_timestamp():
		"""Return the current timestamp, nanoseconds since epoch."""
		return int(time.time() * 1000000000)


	def send_simple(self, address, timestamp, value):
		"""Queue a simple datapoint (ie. a 64-bit word), return True/False for success.

		Arguments:
		address -- uint64_t representing a unique metric.
		timestamp -- uint64_t representing number of nanoseconds (10^-9) since epoch.
		value -- uint64_t value being stored.

		There are no formal restrictions on how `address` is chosen,
		but it must be unique to the metric you are inserting. If you
		don't have one, you may generate one by calling
		`hash_identifier` with a string; the recommended input is the
		source identifier.

		If you don't have a `timestamp` you may pass in None to have
		Pymarquise generate one for you.
		"""
		if self.marquise_ctx is None:
			raise ValueError("Attempted to write to a closed Marquise handle.")

		self.__debug("Supplied address: {}".format(address))

		if timestamp is None:
			timestamp = self.current_timestamp()

		# Wrap/convert our arguments to C datatypes before dispatching.
		# FFI will take care of converting them to the right endianness. I think.
		c_address =   FFI.cast("uint64_t", address)
		c_timestamp = FFI.cast("uint64_t", timestamp)
		c_value =     FFI.cast("uint64_t", value)

		success = C_LIBMARQUISE.marquise_send_simple(self.marquise_ctx, c_address, c_timestamp, c_value)
		self.__debug("send_simple returned {}".format(success))
		if success != 0:
			raise RuntimeError("send_simple was unsuccessful, errno is {}".format(FFI.errno))

		return True


	def send_extended(self, address, timestamp, value):
		"""Queue an extended datapoint (ie. a string), return True/False for success.

		Arguments:
		address -- uint64_t representing a unique metric.
		timestamp -- uint64_t representing number of nanoseconds (10^-9) since epoch.
		value -- string value being stored.
		"""
		if self.marquise_ctx is None:
			raise ValueError("Attempted to write to a closed Marquise handle.")

		self.__debug("Supplied address: {}".format(address))

		if timestamp is None:
			timestamp = self.current_timestamp()

		# Use cast() here to make up the C datatypes for dispatch.
		# FFI will take care of converting them to the right endianness. I think.
		c_address =   FFI.cast("uint64_t", address)
		c_timestamp = FFI.cast("uint64_t", timestamp)
		# c_value needs to be a byte array with a length in bytes
		c_value =     cstring(value)
		c_length =    FFI.cast("size_t", len_cstring(value))
		self.__debug("Sending extended value '{}' with length of {}".format(value, c_length))

		success = C_LIBMARQUISE.marquise_send_extended(self.marquise_ctx, c_address, c_timestamp, c_value, c_length);
		self.__debug("send_extended returned {}".format(success))
		if success != 0:
			raise RuntimeError("send_extended was unsuccessful, errno is {}".format(FFI.errno))

		return True


	def update_source(self, address, metadata_dict):
		"""Pack the `metadata_dict` for an `address` into a data structure and ship it to the spool file.

		Arguments:
		address -- the address for which this metadata_dict applies.
		metadata_dict -- a Python dict of arbitrary string key-value pairs.
		"""
		if self.marquise_ctx is None:
			raise ValueError("Attempted to write to a closed Marquise handle.")

		self.__debug("Supplied address: {}".format(address))

		# Sanity check the input, everything must be UTF8 strings (not
		# yet confirmed), no Nonetypes or anything stupid like that.
		#
		# The keys of the key-value pairs are unique, by virtue of
		# taking a dict as input.
		if any([ x is None for x in metadata_dict.keys() ]):
			raise TypeError("One of your metadata_dict keys is a Nonetype")
		if any([ x is None for x in metadata_dict.values() ]):
			raise TypeError("One of your metadata_dict values is a Nonetype")

		# Cast each string to a C-string
		# XXX: This will have unusual results if the inputs are
		# non-strings, eg. bools become a zero-length string and
		# numbers are also zero-length but get memory malloc'd
		# corresponding to their magnitude. Should probably pass
		# everything through str() first to sanitise.
		try:                   c_fields = [ cstring(x) for x in metadata_dict.keys() ]
		except Exception as e: raise TypeError("One of your metadata_dict keys couldn't be cast to a Cstring, {}".format(e))

		try:                   c_values = [ cstring(x) for x in metadata_dict.values() ]
		except Exception as e: raise TypeError("One of your metadata_dict values couldn't be cast to a Cstring, {}".format(e))

		# Get our source_dict data structure
		source_dict = C_LIBMARQUISE.marquise_new_source(c_fields, c_values, len(metadata_dict))
		if is_cnull(source_dict):
			raise ValueError("errno is set to EINVAL on invalid input, our errno is {}".format(FFI.errno))

		# If you do something stupid, like passing a string where an
		# int (address) is meant to go, CFFI will explode. Which is
		# fine, but that causes memory leaks. The explosion still
		# occurs, but we cleanup after (before?) ourselves.
		try:
			success = C_LIBMARQUISE.marquise_update_source(self.marquise_ctx, address, source_dict)
		except TypeError as e:
			C_LIBMARQUISE.marquise_free_source(source_dict)
			raise

		self.__debug("marquise_update_source returned {}".format(success))
		if success != 0:
			C_LIBMARQUISE.marquise_free_source(source_dict)
			raise RuntimeError("marquise_update_source was unsuccessful, errno is {}".format(FFI.errno))

		C_LIBMARQUISE.marquise_free_source(source_dict)
		return True
