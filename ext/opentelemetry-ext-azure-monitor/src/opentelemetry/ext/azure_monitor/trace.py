# Copyright 2019, OpenTelemetry Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from opentelemetry import trace as trace_api
from opentelemetry.ext.azure_monitor import protocol
from opentelemetry.ext.azure_monitor import util
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.sdk.util import ns_to_iso_str
from urllib.parse import urlparse


class AzureMonitorSpanExporter(SpanExporter):
    def __init__(self, **options):
        self.options = util.Options(**options)
        if not self.options.instrumentation_key:
            raise ValueError("The instrumentation_key is not provided.")

    def export(self, spans):
        for span in spans:
            print(span)  # TODO: add actual implementation here
            print(self.span_to_envelope(span))
        return SpanExportResult.SUCCESS

    @staticmethod
    def ns_to_duration(nanoseconds):
        n = (nanoseconds + 500000) // 1000000  # duration in milliseconds
        n, ms = divmod(n, 1000)
        n, s = divmod(n, 60)
        n, m = divmod(n, 60)
        d, h = divmod(n, 24)
        return "{:d}.{:02d}:{:02d}:{:02d}.{:03d}".format(d, h, m, s, ms)

    def span_to_envelope(self, span):
        envelope = protocol.Envelope(
            iKey=self.options.instrumentation_key,
            tags=dict(util.azure_monitor_context),
            time=ns_to_iso_str(span.start_time),
        )
        envelope.tags["ai.operation.id"] = "{:032x}".format(span.context.trace_id)
        if span.parent:
            envelope.tags["ai.operation.parentId"] = "|{:032x}.{:016x}.".format(
                span.context.trace_id,
                span.parent.span_id,
            )
        if span.kind in (trace_api.SpanKind.SERVER, trace_api.SpanKind.CONSUMER):
            envelope.name = "Microsoft.ApplicationInsights.Request"
            data = protocol.Request(
                id="|{:032x}.{:016x}.".format(span.context.trace_id, span.context.span_id),
                duration=self.ns_to_duration(span.end_time - span.start_time),
                responseCode="0",
                success=False,
                properties={},
            )
            envelope.data = protocol.Data(baseData=data, baseType="RequestData")
            if "http.method" in span.attributes:
                data.name = span.attributes["http.method"]
            if "http.route" in span.attributes:
                data.name = data.name + " " + span.attributes["http.route"]
                envelope.tags["ai.operation.name"] = data.name
            if "http.url" in span.attributes:
                data.url = span.attributes["http.url"]
            if "http.status_code" in span.attributes:
                status_code = span.attributes["http.status_code"]
                data.responseCode = str(status_code)
                data.success = (
                    status_code >= 200 and status_code <= 399
                )
        else:
            envelope.name = \
                "Microsoft.ApplicationInsights.RemoteDependency"
            data = protocol.RemoteDependency(
                name=span.name,  # TODO
                id="|{:032x}.{:016x}.".format(span.context.trace_id, span.context.span_id),
                resultCode="0",  # TODO
                duration=self.ns_to_duration(span.end_time - span.start_time),
                success=True,  # TODO
                properties={},
            )
            envelope.data = protocol.Data(
                baseData=data,
                baseType="RemoteDependencyData",
            )
            if span.kind in (trace_api.SpanKind.CLIENT, trace_api.SpanKind.PRODUCER):
                data.type = "HTTP"  # TODO
                if "http.url" in span.attributes:
                    url = span.attributes["http.url"]
                    # TODO: error handling, probably put scheme as well
                    data.name = urlparse(url).netloc
                if "http.status_code" in span.attributes:
                    data.resultCode = str(span.attributes["http.status_code"])
            else: # SpanKind.INTERNAL
                data.type = "InProc"
        # TODO: links, tracestate, tags
        for key in span.attributes:
            # This removes redundant data from ApplicationInsights
            if key.startswith("http."):
                continue
            data.properties[key] = span.attributes[key]
        return envelope
