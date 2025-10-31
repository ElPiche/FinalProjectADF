package com.da.extractor.service;

import com.da.extractor.entity.kb.KbMongo;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoCursor;
import com.mongodb.client.model.Aggregates;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.changestream.ChangeStreamDocument;
import com.mongodb.client.model.changestream.FullDocument;
import com.mongodb.client.model.changestream.OperationType;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.extern.slf4j.Slf4j;
import org.bson.Document;
import org.bson.conversions.Bson;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.concurrent.ExecutorService;

@Slf4j
@Service
public class KbConfigReaderService {

    private final BatchModeService batchModeService;
    private final StreamingModeService streamingModeService;

    private static final String COLLECTION = "kb_configs";

    private final MongoTemplate mongoTemplate;
    private final ExecutorService executor;
    private volatile boolean running = true;

    public KbConfigReaderService(BatchModeService batchModeService,
                                 StreamingModeService streamingModeService,
                                 @Qualifier("knowledgeBaseMongoTemplate") MongoTemplate mongoTemplate,
                                 @Qualifier("changeStreamExecutor") ExecutorService executor) {
        this.batchModeService = batchModeService;
        this.streamingModeService = streamingModeService;
        this.mongoTemplate = mongoTemplate;
        this.executor = executor;
    }

    @PostConstruct
    void start() {
        executor.submit(this::runStream);
    }

    private void runStream () {
        // Listener resiliente para la colección kb_configs transformando a KbMongo
        MongoCollection<Document> collection = mongoTemplate.getCollection(COLLECTION);
        // Pipeline simple: escuchar cualquier operación soportada (insert/update/replace/delete)
        List<Bson> pipeline = List.of(
                Aggregates.match(Filters.in("operationType", List.of("insert", "update", "replace")))
        );
        int retry = 0;
        while (running) {
            try (MongoCursor<ChangeStreamDocument<Document>> cursor = collection
                    .watch(pipeline)
                    .fullDocument(FullDocument.UPDATE_LOOKUP)
                    .iterator()) {

                log.info("[KB ChangeStream] Iniciado sobre colección '{}'", COLLECTION);
                retry = 0; // reset de reintentos al conectar
                while (running && cursor.hasNext()) {
                    ChangeStreamDocument<Document> change = cursor.next();
                    String op = change.getOperationType() != null ? change.getOperationType().getValue() : "unknown";
                    Document full = change.getFullDocument();

                    if (full != null) {
                        // Convertir a entidad tipada
                        KbMongo kb = mongoTemplate.getConverter().read(KbMongo.class, full);

                        OperationType operationType = change.getOperationType();
                        if (operationType == OperationType.INSERT || operationType == OperationType.UPDATE) {
                            batchModeService.executeConfiguration(kb);
                            streamingModeService.executeConfiguration(kb);
                        }

                        log.info("[KB ChangeStream] op={} id={} name={} changeFlag={}", op, kb.getId(), kb.getName(), kb.getChangeFlag());
                        // Aquí se puede disparar lógica adicional (ej: publicar evento interno, refrescar caché, etc.)
                    } else {
                        // Para deletes u operaciones sin cuerpo completo
                        log.info("[KB ChangeStream] op={} key={} (sin fullDocument)", op, change.getDocumentKey());
                    }
                }
            } catch (Exception e) {
                long backoffMillis = Math.min(10_000, (long) Math.pow(2, Math.min(retry, 5)) * 250L);
                log.warn("[KB ChangeStream] Error en stream (reintento {} en {} ms): {}", retry, backoffMillis, e.getMessage(), e);
                try { Thread.sleep(backoffMillis); } catch (InterruptedException ie) { Thread.currentThread().interrupt(); }
                retry++;
            }
        }
        log.info("[KB ChangeStream] Finalizado");
    }

    // Método opcional para apagar limpiamente (también invocado automáticamente en shutdown del contexto)
    @PreDestroy
    public void stop() {
        running = false;
        executor.shutdownNow();
    }
}
