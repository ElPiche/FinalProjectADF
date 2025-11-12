# Etapa de construcción
FROM maven:latest AS build

# Establecer directorio de trabajo
WORKDIR /app

# Copiar archivos de configuración de Maven
COPY pom.xml .
COPY mvnw .
COPY mvnw.cmd .
COPY .mvn .mvn

# Descargar dependencias (para cachear esta capa)
RUN mvn dependency:go-offline -B

# Copiar código fuente
COPY src ./src

# Compilar la aplicación
RUN mvn clean package -DskipTests

# Etapa de ejecución
FROM eclipse-temurin:25-jdk

# Paquetes de networking útiles para debugging
#RUN apt-get update && apt-get install -y net-tools iputils-ping telnet && apt-get clean && rm -rf /var/lib/apt/lists/*

# Crear usuario no root para seguridad
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Establecer directorio de trabajo
WORKDIR /app

# Copiar el JAR compilado desde la etapa de construcción
COPY --from=build /app/target/extractor-*.jar app.jar

# Cambiar permisos y propietario
RUN chown -R appuser:appuser /app
USER appuser

# Exponer puerto (ajustar según el puerto que use tu aplicación)
EXPOSE 8080

# Variables de entorno
ENV JAVA_OPTS="-Xmx512m -Xms256m"

# Comando de ejecución
ENTRYPOINT ["sh", "-c", "java $JAVA_OPTS -Djava.security.egd=file:/dev/./urandom -jar app.jar"]